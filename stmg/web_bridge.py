# -*- coding: utf-8 -*-
"""STMG 网页版引擎桥 —— 在 Pyodide（WebAssembly 里的 CPython）中跑**真正的引擎**。

网页版的 JS 只负责画界面、收键盘；剧本的解析、变量求值、分支推进
全部交给这个文件背后的 Python 引擎。所以网页版和桌面版跑的是同一套
逻辑，不会出现「网页里这样、桌面上那样」的偏差。

接口就一个类：

    d = Driver(script_text, options_text)
    d.next(None)        -> 一条事件的 JSON（say / choose / bg / sprite / bgm ...）
    d.next("选项名")     -> 把玩家的回答送回剧本，返回下一条事件
    d.next("输入的文字")  -> 同上（问玩家名字那种）
    剧本跑完返回 {"t": "__done__"}

事件类型和桌面版完全一致，见 stmg/runtime.py 顶部的说明。

网页比桌面多出来的两件事，都在这个文件里兜住：

**① R.api 的异步**（第 2 期 #12）
    浏览器里没有「同步阻塞的 socket」，Python 侧又没法 await JS 的 fetch。
    所以 R.api 走「挂起 → 交给 JS 去 fetch → 重建执行流接回去」：
    引擎跑到 R.api 时不去发请求，而是抛一个 `_PendingAPI` 把请求冒泡出来，
    `next()` 把它变成一条 `{"t": "api_pending"}` 事件交给页面；
    页面 fetch 完调 `resolve_api()` 把结果塞进缓存，下一拍 Driver 重新
    起一个生成器、把记下来的 `answers` 喂回去，重跑一遍，
    走出和第一次一模一样的路，接在挂起点后面继续。

    停在哪儿是用 **api 序号** 认的，不是数事件条数：同一个剧本「首轮」和
    「重放」产出的事件数并不一样（`stm.os` 只在重放时才吐 `os_result`），
    拿条数当进度迟早对不上，会漏事件甚至把台词放两遍。序号则一定对得上。
    重跑本身是安全的：剧本里的选择 / 随机 / 文件操作都有 `answers` 记录，
    重跑只重放结果、不再真的执行一遍（这也是存档重放用的同一套机制）。

**② stm.os 的沙箱虚拟文件系统**（第 2 期 #12）
    网页版绝不碰玩家真实磁盘。四个动作（read / create / remove / revision）
    全部落到一份**内存镜像**上，语义和桌面版 stmos 对齐：
    remove 进虚拟回收站 `.trash/`，revision 先留一份 `.bak`。
    IndexedDB 只有异步接口，Python 侧没法 await，所以持久化交给 JS：
    每个事件之后页面调 `vfs_changes()` 把改动取走写进 IndexedDB；
    启动时页面先读 IndexedDB，再 `load_vfs()` 灌回来。
"""

import json

from stmg import options as optmod
from stmg import parser
from stmg import stdlib_api
from stmg import stmos
from stmg.runtime import Runtime

# R.api 的超时（毫秒），由页面上的 fetch 执行；契约要求 10 秒
API_TIMEOUT_MS = 10000

# 同一个请求最多交回给页面几次；页面一直不给结果就放弃，别把剧情卡死
MAX_API_TRIES = 3

# 联网失败时替换掉引擎那句干巴巴的「R.api 失败：None」
API_FAIL_TEXT = ("网页版联网没成功（超时 / 被跨域 CORS 挡住 / 断网），"
                 "STM.API 是空的，剧情照常往下走")

# 沙箱文件系统用不了时的提示（只说一次）
VFS_DOWN_TEXT = "网页版沙箱文件系统用不了（浏览器不支持或你拒绝了），stm.os 已跳过"


class _PendingAPI(BaseException):
    """R.api 在网页版里没法同步等：用它把「要发的请求」冒泡给 JS。

    注意继承的是 **BaseException** 而不是 Exception —— runtime.run() 里有一层
    `except Exception`（把引擎异常包成 fatal 事件），继承 Exception 会被它吞掉，
    请求就永远送不到页面上了。
    """

    def __init__(self, n, url, key):
        BaseException.__init__(self)
        self.n = n          # 这次请求在整份剧本里排第几（从 1 开始）
        self.url = url
        self.key = key


# 当前正在跑的 Driver。Pyodide 是单线程、一次只跑一个剧本，所以用模块级变量
# 把「被打了桩的 stdlib_api.call_api / stmos.*」接回实例。
_ACTIVE = None


def _rel(path):
    """把引擎解析出来的虚拟路径还原成项目内的相对路径，前端好找素材。"""
    p = str(path or "").replace("\\", "/")
    i = p.find("/game/")
    if i >= 0:
        return p[i + 6:]
    return p


# --------------------------------------------------------------------------- #
# 沙箱虚拟文件系统（Python 侧的内存镜像）
# --------------------------------------------------------------------------- #
class VirtualFS(object):
    """stm.os 在浏览器里的「磁盘」。

    这里只是一份内存镜像，真正的持久化在 JS 那边的 IndexedDB。
    语义严格对齐桌面版 stmg/stmos.py：

        read     读内容，读不到返回 (False, "")
        create   建空文件，已存在就不动
        remove   **移进虚拟回收站**，不是永久删除，能找回
        revision 改内容前先留一份 `.bak`，改坏了能还原

    另外：不管剧本里的路径写成 `C:/Users/xxx/a.txt` 还是
    `stmg-virtual://save/a.txt`，都只是这份镜像里的一个键——
    网页版碰不到真实磁盘，这是硬保证。
    """

    TRASH = ".trash"

    SCHEME = "stmg-virtual:"

    def __init__(self):
        self.files = {}          # "a/b/c.txt" -> 内容
        self.dirty = {}          # 还没有同步给 IndexedDB 的改动：路径 -> 新内容 / None=删除
        self.enabled = True      # 浏览器不支持或用户拒绝时置 False，全体降级
        self._warned = False
        self._root = ""          # 引擎眼里的项目根目录，归一化时剥掉

    def set_root(self, root):
        """记下引擎的项目根目录。

        剧本里写相对路径时，runtime 会把它拼成 `<root>/notes/a.txt`；
        写 `stmg-virtual://notes/a.txt` 时又不会拼。两种写法剥掉根目录后
        指向同一个文件，玩家不用关心自己写的是哪一种。
        """
        self._root = self._norm(str(root or ""), strip_root=False)

    # -- 路径归一化 ------------------------------------------------------ #
    def norm(self, path):
        """任何写法都归一成镜像里的键：去掉协议 / 盘符 / 项目根目录，折叠 `..`。"""
        return self._norm(str(path or ""), strip_root=True)

    def _norm(self, path, strip_root):
        p = path.strip().replace("\\", "/")
        # `stmg-virtual://x` 可能出现被 resolve() 拼到根目录后面的形式
        # （如 `/game/stmg-virtual://x`），所以按「第一次出现」切，不看开头
        i = p.lower().find(self.SCHEME)
        if i >= 0:
            p = p[i + len(self.SCHEME):]
        elif len(p) > 1 and p[1] == ":":        # 吃掉 C: / D: 这样的盘符
            p = p[2:]
        parts = []
        for seg in p.split("/"):
            seg = seg.strip()
            if seg in ("", "."):
                continue
            if seg == "..":
                if parts:
                    parts.pop()
                continue
            parts.append(seg)
        k = "/".join(parts)
        if strip_root and self._root:
            if k == self._root:
                return ""
            if k.startswith(self._root + "/"):
                k = k[len(self._root) + 1:]
        return k

    def _set(self, key, content):
        if content is None:
            self.files.pop(key, None)
        else:
            self.files[key] = content
        self.dirty[key] = content

    # -- 降级 ------------------------------------------------------------ #
    def degraded(self):
        """标记「用不了」，返回提示文案（只在第一次给文案）。"""
        if self._warned:
            return ""
        self._warned = True
        return VFS_DOWN_TEXT

    # -- 四个动作（对齐桌面版 stmos 的返回值） ---------------------------- #
    def read(self, path):
        if not self.enabled:
            return False, ""
        k = self.norm(path)
        if not k:
            return False, ""
        return (True, self.files[k]) if k in self.files else (False, "")

    def create(self, path):
        if not self.enabled:
            return False, "沙箱不可用"
        k = self.norm(path)
        if not k:
            return False, "没给路径"
        if k in self.files:
            return True, "已存在，未改动"
        self._set(k, "")
        return True, ""

    def remove(self, path):
        if not self.enabled:
            return False, "沙箱不可用"
        k = self.norm(path)
        if not k:
            return False, "没给路径"
        if k not in self.files:
            return True, "不存在，跳过"
        # 桌面版走系统回收站；网页版走虚拟回收站，同样「误删能找回」
        name = k.split("/")[-1]
        dest = "%s/%s" % (self.TRASH, name)
        i = 1
        while dest in self.files:
            i += 1
            dest = "%s/%s.%d" % (self.TRASH, name, i)
        self._set(dest, self.files[k])
        self._set(k, None)
        return True, ""

    def revision(self, path, old, new):
        if not self.enabled:
            return False, "沙箱不可用"
        if old is None or new is None:
            return False, "revision 需要 ,\"旧内容\"to\"新内容\""
        k = self.norm(path)
        if not k:
            return False, "没给路径"
        if k not in self.files:
            return False, "文件不存在"
        self._set(k + ".bak", self.files[k])          # 先备份，和桌面版一样
        self._set(k, self.files[k].replace(old, new) if old else new)
        return True, ""

    # -- 和页面同步 ------------------------------------------------------ #
    def take_changes(self):
        """把「还没落盘的改动」交给页面去写 IndexedDB；没改动返回 None。"""
        if not self.dirty:
            return None
        add, drop = {}, []
        for k, v in self.dirty.items():
            if v is None:
                drop.append(k)
            else:
                add[k] = v
        self.dirty = {}
        return {"set": add, "del": drop}


# --------------------------------------------------------------------------- #
# 给引擎打的桩
# --------------------------------------------------------------------------- #
def _call_api(url="", key="", method="GET", params=None, data=None):
    """stdlib_api.call_api 的网页版实现：不真发请求，交给页面去 fetch。"""
    drv = _ACTIVE
    if drv is None:
        return False, "网页版还没有引擎在跑，联网请求被跳过"
    return drv.ask_api(url, key)


def _web_read_file(path):
    drv = _ACTIVE
    if drv is None:
        return False, ""
    return drv.vfs.read(path)


def _web_create_file(path):
    drv = _ACTIVE
    if drv is None:
        return False, "网页版还没有引擎在跑"
    return drv.vfs.create(path)


def _web_remove_file(path):
    drv = _ACTIVE
    if drv is None:
        return False, "网页版还没有引擎在跑"
    return drv.vfs.remove(path)


def _web_revision_file(path, old, new):
    drv = _ACTIVE
    if drv is None:
        return False, "网页版还没有引擎在跑"
    return drv.vfs.revision(path, old, new)


stdlib_api.call_api = _call_api
stmos.read_file = _web_read_file
stmos.create_file = _web_create_file
stmos.remove_file = _web_remove_file
stmos.revision_file = _web_revision_file


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
class Driver(object):
    def __init__(self, script_text, options_text="", script_path="/game/script.stm"):
        # script_path 只是个「引擎眼里的剧本路径」：Pyodide 里是 /game/script.stm
        # （MEMFS 里的假路径，成就 / CG 这类小文件写在那儿，重启就没了）。
        # 留成参数是为了让自测能指到临时目录，不去碰真实磁盘。
        global _ACTIVE
        self.script = parser.parse_text(script_text, script_path)
        try:
            self.opt = optmod.parse_options_text(options_text) if options_text else {}
        except Exception:                              # noqa: BLE001
            self.opt = {}
        self.vfs = VirtualFS()
        self.api_cache = {}          # 请求序号 -> (ok, result)
        self.api_tries = {}          # 请求序号 -> 已交给页面几次
        self.delivered = 0           # 已经发给页面的「引擎事件」条数（统计用）
        self.asked = 0               # 其中有多少条是 choose / question
        self.queue = []              # 下一拍要先吐出来的事件（降级提示用）
        self.toast_once = ""         # 攒着的一条提示，插到下一个事件前面
        self.skip_until_api = 0      # >0：正在补跑，直到撞上这个序号的请求为止
        self.pending_n = 0           # 已经交给页面 fetch、还没等到结果的请求序号
        self.done = False
        self._reset()
        _ACTIVE = self

    # ------------------------------------------------------------------ #
    # 执行流
    # ------------------------------------------------------------------ #
    def _reset(self):
        """从剧本开头重建执行流（第一次跑 / 补跑都用它）。"""
        self.rt = Runtime(self.script, self.opt, dev_mode=False)
        self.gen = self.rt.run()
        self.vfs.set_root(self.rt.root)
        self.delivered = 0
        self.asked = 0
        self.skip_until_api = 0
        self.pending_n = 0

    def _resume(self, n):
        """页面把第 n 个请求的结果送回来了 —— 重建执行流、接回挂起点。

        为什么要重建：Python 侧没法 await 页面的 fetch，R.api 只能先把请求
        冒泡出去，那个生成器已经死在异常里、接不回来了。所以换一个新的，
        把之前记下的 `answers` 原样喂回去，它会走出和第一次完全一样的路。

        怎么知道「已经跑完挂起点之前的那些」：`ask_api` 每次被叫到都会报出
        自己是第几个请求，撞上 n 就说明前面都跑完了 —— 从那一刻起的事件
        才是页面还没看过的。**用序号而不是事件条数**，是因为首轮和重放产出
        的事件条数本来就不一样（见文件头说明），数条数会算错账。
        """
        replay = list(self.rt.answers)
        self.rt = Runtime(self.script, self.opt, dev_mode=False)
        self.gen = self.rt.run(replay=replay)
        self.vfs.set_root(self.rt.root)
        self.skip_until_api = n
        self.pending_n = 0

    # ------------------------------------------------------------------ #
    # R.api
    # ------------------------------------------------------------------ #
    def _api_ordinal(self):
        """这次 api 调用在整份剧本里排第几。

        已经被回放短路掉的请求也会记在 `answers` 里，一起数进来，
        这样重跑之后序号仍然对得上（缓存不会串位）。
        """
        k = 0
        for item in self.rt.answers:
            if item and item[0] == "api":
                k += 1
        return k + 1

    def ask_api(self, url, key):
        """引擎问「这个 URL 的结果是什么」。有缓存直接给，没有就挂起。"""
        n = self._api_ordinal()
        if self.skip_until_api and n >= self.skip_until_api:
            # 补跑跑到挂起点了：从这里开始的事件页面都还没看过，别再丢了
            self.skip_until_api = 0
        if n in self.api_cache:
            return self.api_cache[n]
        raise _PendingAPI(n, str(url or ""), str(key or ""))

    def _on_pending(self, p):
        """把挂起的请求变成一条事件交给页面，等它 fetch 完再叫我们。"""
        n = p.n
        tries = self.api_tries.get(n, 0) + 1
        self.api_tries[n] = tries
        if tries > MAX_API_TRIES:
            # 页面一直没把结果送回来：直接当失败处理，别把剧情卡死
            self.api_cache[n] = (False, None)
            self._resume(n)
            return self.next(None)
        self.pending_n = n
        return json.dumps({"t": "api_pending", "n": n, "url": p.url, "key": p.key,
                           "timeout": API_TIMEOUT_MS, "tries": tries},
                          ensure_ascii=False)

    # ------------------------------------------------------------------ #
    # 对外接口
    # ------------------------------------------------------------------ #
    def next(self, answer=None):
        while True:
            if self.queue:
                return json.dumps(self.queue.pop(0), ensure_ascii=False)
            if self.done:
                return json.dumps({"t": "__done__"})
            if self.pending_n:
                # 有请求挂起过：新一轮进来就是重建执行流、接回挂起点。
                # 页面还没把结果送回来的话，重跑会再挂起一次（tries 兜底）。
                self._resume(self.pending_n)
            try:
                ev = self.gen.send(answer)
            except StopIteration:
                self.done = True
                return json.dumps({"t": "__done__"})
            except _PendingAPI as p:
                return self._on_pending(p)
            except BaseException as e:                      # noqa: BLE001
                self.done = True
                return json.dumps({"t": "fatal",
                                   "message": "%s: %s" % (type(e).__name__, e)})
            answer = None
            out = self._emit(ev)
            if out is None:
                continue            # 补跑阶段：这条页面早看过了，丢掉
            return out

    def _emit(self, ev):
        """整理并交出一条事件；补跑阶段返回 None 表示「这条丢掉」。"""
        if self.skip_until_api:
            return None
        ev = dict(ev)
        if ev.get("path"):
            ev["path"] = _rel(ev["path"])
        ev = self._polish(ev)
        self.delivered += 1
        if ev.get("t") in ("choose", "question"):
            self.asked += 1
        self._sync_vfs_state()
        if self.toast_once:
            text, self.toast_once = self.toast_once, ""
            self.queue.append(ev)               # 真事件挪到下一拍，别被提示顶掉
            return json.dumps({"t": "toast", "text": text}, ensure_ascii=False)
        return json.dumps(ev, ensure_ascii=False)

    def _polish(self, ev):
        """把引擎吐出来的事件顺手修一下（只动文案，不动语义）。"""
        if ev.get("t") == "toast":
            t = str(ev.get("text") or "")
            if t.startswith("R.api 失败"):
                ev["text"] = API_FAIL_TEXT
        return ev

    def _queue_toast(self, text):
        if text and not self.toast_once:
            self.toast_once = text

    def _sync_vfs_state(self):
        """沙箱被降级时，攒一句提示插到事件流里。"""
        if not self.vfs.enabled and not self.vfs._warned:
            self._queue_toast(self.vfs.degraded())

    # -- 页面回调 -------------------------------------------------------- #
    def resolve_api(self, n, ok, result=None):
        """页面 fetch 完之后把结果送回来。"""
        try:
            n = int(n)
        except (TypeError, ValueError):
            return json.dumps({"ok": False, "why": "n 不是整数"}, ensure_ascii=False)
        if result is not None and not isinstance(result, str):
            result = str(result)
        self.api_cache[n] = (bool(ok), result)
        return json.dumps({"ok": True, "n": n}, ensure_ascii=False)

    def vfs_changes(self):
        """页面每拿到一条事件就调一次：把还没落盘的沙箱改动取走。"""
        ch = self.vfs.take_changes()
        return json.dumps(ch, ensure_ascii=False) if ch else "null"

    def load_vfs(self, text):
        """页面读完 IndexedDB 之后，把沙箱文件灌回来。"""
        try:
            data = json.loads(text) if text else {}
        except Exception:                               # noqa: BLE001
            return json.dumps({"ok": False, "n": 0, "why": "不是合法的 JSON"},
                              ensure_ascii=False)
        if not isinstance(data, dict):
            data = {}
        n = 0
        for k, v in data.items():
            kk = self.vfs.norm(k)
            if kk and isinstance(v, str):
                self.vfs.files[kk] = v
                n += 1
        return json.dumps({"ok": True, "n": n}, ensure_ascii=False)

    def set_vfs_enabled(self, flag):
        """页面告诉引擎沙箱能不能用；不能就全体降级成「跳过 + 提示」。"""
        self.vfs.enabled = bool(flag)
        if not self.vfs.enabled:
            self._sync_vfs_state()
        return json.dumps({"ok": True, "enabled": self.vfs.enabled},
                          ensure_ascii=False)

    # ------------------------------------------------------------------ #
    def info(self):
        """给前端的一点点元信息。"""
        return json.dumps({"title": self.script.title,
                           "w": self.script.width, "h": self.script.height,
                           "ver": self.script.header.get("ver", "1.0.0"),
                           "errors": self.script.error_count(),
                           "api_timeout": API_TIMEOUT_MS},
                          ensure_ascii=False)
