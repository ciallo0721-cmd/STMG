# -*- coding: utf-8 -*-
"""STMG 运行时 —— 把语句树解释成一条「事件流」。

用生成器实现：调用方 `next()` 拿事件，`send()` 把玩家的回答塞回去。
这样渲染层不用关心剧本结构，剧本也不用关心窗口。

事件类型：
    say      一句台词 / 旁白          who(可为 None), text, color
    choose   等玩家选                options
    question 等玩家打字              prompt
    bg       换背景                  path
    picture  背景上的图片层          path(空则清除)
    sprite   立绘                    path(空则隐藏)
    bgm/se/voice  音频               path, loop
    stop/hide    停音频 / 隐藏图层   what
    transition  转场遮罩              kind, dur
    toast    右上角提示              text
    python   STM.python 载入         name
    fatal    跑不动了                message, trace
    end      剧本结束
"""

import os
import random
import re
import types

from . import pack, save as savemod, stdlib_api, stmos
from .errors import STMFatal, format_exception
from .markdown import strip_quotes

NAME_COLORS = ["#ff88bb", "#7fb3ff", "#6fd6a8", "#ffc44d",
               "#c79bff", "#ff9d7a", "#5fc9d6"]

SAFE_BUILTINS = {
    "abs": abs, "min": min, "max": max, "len": len, "str": str,
    "int": int, "float": float, "round": round, "bool": bool,
    "range": range, "sum": sum, "sorted": sorted, "list": list,
    "dict": dict, "enumerate": enumerate, "zip": zip,
}

# 回放感知随机：
#   - 正常跑：把每次随机数写进 answers 流（("rand", v)），随存档一起保存；
#   - 回放（读档重放）时：RAND 不再新抽，而是按记录原样吐出，
#     于是带随机分支的剧情重载后走向完全一致。
# RAND 需要访问「当前 Runtime 的回放状态」，但 SAFE_BUILTINS 是模块级共享表，
# 所以函数体通过全局 _ACTIVE_RUNTIME 在求值时拿到实例（引擎单线程，安全）。
_ACTIVE_RUNTIME = None


def RAND(a, b):
    """回放感知随机：返回 [a, b] 闭区间内的整数（含两端）。"""
    rt = _ACTIVE_RUNTIME
    if rt is not None:
        return rt._rand_draw(a, b)
    return random.randint(int(a), int(b))


# 把随机函数加进安全内建表，让剧本表达式里能直接写 RAND(1,6) / randint(1,6)
SAFE_BUILTINS = dict(SAFE_BUILTINS)
SAFE_BUILTINS["randint"] = RAND
SAFE_BUILTINS["RAND"] = RAND

IDENT_RE = re.compile(r"^[A-Za-z_\u4e00-\u9fff]\w*$")
NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def _is_str_literal(s):
    """s 是不是「一个完整的字符串字面量」。

    `"你好"` 是；`"你好" + STM.ANSWER` 不是（里面有第二对引号）。
    分不清这两种，拼字符串就永远会被当成普通文本原样打出来。
    """
    if not isinstance(s, str) or len(s) < 2:
        return False
    if not (s[0] == '"' and s[-1] == '"'):
        return False
    return '"' not in s[1:-1]


class JumpSignal(Exception):
    """S.jump("标签") 内部用。"""

    def __init__(self, index):
        Exception.__init__(self)
        self.index = index


class Runtime(object):
    def __init__(self, script, options=None, dev_mode=True):
        self.script = script
        self.options = options
        self.dev_mode = dev_mode
        self.root = os.path.dirname(os.path.abspath(script.path))

        self.STM = types.SimpleNamespace(Q="", ANSWER="", NAME="", API=None, OS="")
        self.vars = {"STM": self.STM, "R": types.SimpleNamespace(RESULT=None)}
        self.names = {}
        self.chosen = set()
        self.last_choice = None
        self.history = []
        self.answers = []          # 存档用：[("choose", 选项名), ("question", 输入)]
        self._libraries = {}
        self._replay = []
        self._replay_i = 0
        self._labels = {s["name"]: i for i, s in enumerate(script.body)
                        if s["k"] == "label"}

        # 成就系统：已解锁集合（跨会话持久化，按剧本标题区分）。
        # 一开始从存档里读出来；运行中新解锁的会立刻写回。
        self.unlocked = savemod.load_achievements(self.root, self.script.title)

    # ------------------------------------------------------------------ #
    # 求值
    # ------------------------------------------------------------------ #
    def eval_expr(self, expr):
        expr = (expr or "").strip()
        if not expr:
            return ""
        if _is_str_literal(expr):
            return expr[1:-1]
        if NUM_RE.match(expr):
            return float(expr) if "." in expr else int(expr)
        env = dict(self.vars)
        env.setdefault("STM", self.STM)
        global _ACTIVE_RUNTIME
        _ACTIVE_RUNTIME = self
        try:
            return eval(expr, {"__builtins__": SAFE_BUILTINS}, env)
        except NameError:
            if IDENT_RE.match(expr):
                # 没定义过的裸词，当字符串处理，别直接崩
                return expr
            raise STMFatal("算式里有没定义过的东西：%s" % expr)
        except ZeroDivisionError:
            raise STMFatal("除零了：%s" % expr)
        except Exception as e:                       # noqa: BLE001
            raise STMFatal("算式算不出来：%s（%s）" % (expr, e))
        finally:
            # 求值结束（无论成功或异常）都清掉，避免指向已失效的 Runtime
            _ACTIVE_RUNTIME = None

    def eval_cond(self, cond):
        cond = (cond or "").strip()
        if not cond:
            return True
        if _is_str_literal(cond):
            # If "选项1": —— 判断有没有选过这个名字
            return cond[1:-1] in self.chosen
        return bool(self.eval_expr(cond))

    def resolve(self, path):
        """把剧本里的相对路径变成绝对路径；找不到就原样返回，交给渲染层画占位。"""
        if not path:
            return ""
        p = path.replace("\\", "/")
        if os.path.isabs(p) and os.path.exists(p):
            return p
        pk = pack.active()
        if pk is not None and pk.has(p):
            return pack.PREFIX + p
        return os.path.join(self.root, p)

    # ------------------------------------------------------------------ #
    # 主循环
    # ------------------------------------------------------------------ #
    def run(self, replay=None):
        self._replay = list(replay or [])
        self._replay_i = 0
        body = self.script.body
        i = 0
        try:
            while True:
                try:
                    # 必须用 yield from：它会把 send() 送进来的值一路转交给
                    # 最里面那个 yield，写成 for ... yield 的话玩家输入会被丢掉。
                    yield from self.exec_block(body[i:])
                    break
                except JumpSignal as j:
                    i = j.index
                    continue
            if self.script.ending:
                yield from self.exec_block(self.script.ending)
        except STMFatal as e:
            yield {"t": "fatal", "message": str(e), "trace": ""}
            return
        except Exception as e:                       # noqa: BLE001
            yield {"t": "fatal", "message": "%s: %s" % (type(e).__name__, e),
                   "trace": format_exception(e) if self.dev_mode else ""}
            return
        yield {"t": "end"}

    def exec_block(self, stmts):
        for s in stmts:
            k = s["k"]

            if k == "say":
                text = self._say_text(s["text"])
                who = s["who"]
                ev = {"t": "say", "who": who, "text": text, "line": s["line"]}
                if who:
                    if who not in self.names:
                        self.names[who] = NAME_COLORS[len(self.names) % len(NAME_COLORS)]
                    ev["color"] = self.names[who]
                self.history.append((who or "", text))
                yield ev

            elif k == "choose":
                ev = {"t": "choose", "options": list(s["options"]),
                      "line": s["line"]}
                ans = self._take_answer()
                if ans is None:
                    ans = yield ev
                self.chosen.add(ans)
                self.last_choice = ans
                if not isinstance(ans, str):
                    ans = ev["options"][ans] if isinstance(ans, int) and \
                        ans < len(ev["options"]) else str(ans)
                    self.chosen.add(ans)
                    self.last_choice = ans

            elif k == "if":
                if self.eval_cond(s["cond"]):
                    yield from self.exec_block(s["body"])
                elif s.get("else_body"):
                    yield from self.exec_block(s["else_body"])

            elif k == "else":
                continue

            elif k == "set":
                self._assign(s["name"], self.eval_expr(s["expr"]))

            elif k == "question":
                prompt = strip_quotes(s["prompt"]) if s["prompt"] else ""
                if prompt:
                    self.STM.Q = prompt
                ev = {"t": "question", "prompt": self.STM.Q or "请输入",
                      "line": s["line"]}
                ans = self._take_answer()
                if ans is None:
                    ans = yield ev
                    self.answers.append(("question", ans))
                self.STM.ANSWER = ans
                self.vars["STM.ANSWER"] = ans

            elif k == "define":
                name = s["name"]
                if name and name not in self.names:
                    self.names[name] = NAME_COLORS[len(self.names) % len(NAME_COLORS)]

            elif k == "sprite":
                yield from self._sprite_event(s["path"], s.get("args") or [],
                                              s.get("kwargs") or {})

            elif k == "label":
                continue

            elif k == "call":
                yield from self.do_call(s)

            elif k == "stm_os":
                yield from self.do_stmos(s)

    # ------------------------------------------------------------------ #
    # 内建函数
    # ------------------------------------------------------------------ #
    def do_call(self, s):
        obj = (s["obj"] or "").upper()
        method = s["method"].lower()
        args, kw = s["args"], s["kwargs"]
        a0 = args[0] if args else ""

        # 成就解锁：STM.achieve("名称") 与 ACHIEVE("名称") 都走这里。
        # 只有「第一次解锁」才产生事件，gui 据此弹窗；已解锁的静默跳过。
        if method == "achieve":
            # a0 已由解析器去掉引号，就是干净的成就名（字符串字面量直接可用）；
            # 非字符串（如数字）也转成字符串，空值忽略。
            name = a0 if isinstance(a0, str) else ("" if a0 is None else str(a0))
            if name:
                if name not in self.unlocked:
                    self.unlocked.add(name)
                    savemod.save_achievements(self.root, self.script.title,
                                             self.unlocked)
                    yield {"t": "achieve", "name": name, "is_new": True}
                else:
                    yield {"t": "achieve", "name": name, "is_new": False}
            return

        if obj == "S":
            if method == "character" and a0:          # 兜底，正常走不到
                yield from self._sprite_event(a0, args, kw)
            elif method in ("cg", "bg", "background"):
                # 和 Ren'Py 的 scene 一样：换背景会先把立绘清空
                yield {"t": "bg", "path": self.resolve(a0), "clear": True}
            elif method == "picture":
                yield {"t": "picture", "path": self.resolve(a0)}
            elif method == "play":
                loop = str(kw.get("loop", "true")).lower() not in ("false", "0", "no")
                yield {"t": "bgm", "path": self.resolve(a0), "loop": loop}
            elif method == "sound":
                yield {"t": "se", "path": self.resolve(a0)}
            elif method == "voice":
                yield {"t": "voice", "path": self.resolve(a0)}
            elif method == "stop":
                yield {"t": "stop", "what": (a0 or "bgm").lower()}
            elif method == "hide":
                yield {"t": "hide", "what": (a0 or "sprite").lower()}
            elif method == "transition":
                # 转场：gui 会拿它做全屏遮罩动画（fade / dissolve / flash），
                # 在「上一帧」和「下一帧」之间切换；没写 S.transition 时完全不影响。
                yield {"t": "transition", "kind": (a0 or "fade"),
                       "dur": float(kw.get("dur", "0.4"))}
            elif method == "jump":
                if a0 in self._labels:
                    raise JumpSignal(self._labels[a0] + 1)
                raise STMFatal('S.jump("%s") 找不到这个标签' % a0)
            elif method == "end":
                raise JumpSignal(len(self.script.body))
            else:
                yield {"t": "toast", "text": "S.%s 这个函数还没实现" % s["method"]}

        elif obj == "STM":
            if method == "display":
                yield {"t": "toast", "text": a0}
            elif method == "python":
                ok, why = stdlib_api.check_library(a0)
                if not ok:
                    raise STMFatal("STM.python: " + why)
                if not self.dev_mode:
                    yield {"t": "toast",
                           "text": "发布版不允许 STM.python(%s)，已忽略" % a0}
                else:
                    if a0 in stdlib_api.RELEASE_BLOCKED:
                        yield {"t": "toast",
                               "text": "STM.python(%s) 被标记为仅开发模式可用" % a0}
                    self._libraries[a0] = True
                    yield {"t": "python", "name": a0}
            else:
                yield {"t": "toast", "text": "STM.%s 这个函数还没实现" % s["method"]}

        elif obj == "R":
            if method == "api":
                key = kw.get("key", "")
                if key == "option":
                    key = self.options.get("enc", "") if self.options else ""
                if not self.dev_mode and not self.options.get("allow_net", True):
                    yield {"t": "toast", "text": "发布版已关闭联网，R.api 被忽略"}
                    return
                ok, result = stdlib_api.call_api(kw.get("url", a0), key=key)
                self.STM.API = result
                self.vars["R"].RESULT = result
                yield {"t": "toast",
                       "text": "R.api %s：%s" % ("成功" if ok else "失败",
                                                str(result)[:60])}
            else:
                yield {"t": "toast", "text": "R.%s 这个函数还没实现" % s["method"]}
        else:
            yield {"t": "toast", "text": "不认识的调用：%s" % s["method"]}

    def do_stmos(self, s):
        """stm.os 受控文件操作。设计上**静默**——发布版不弹任何提示，
        这样在玩家机器上做 DDLC 式演出时才不会「穿帮」；只有开发模式
        会把失败原因用 toast 打出来方便调试。"""
        op = (s.get("op") or "").lower()
        path = (s.get("path") or "").replace("\\", "/")
        if not path:
            if self.dev_mode:
                yield {"t": "toast", "text": "stm.os: 没给路径"}
            return
        # 绝对路径直接用；相对路径按项目根目录解析
        p = path if os.path.isabs(path) else self.resolve(path)

        if op == "read":
            ok, content = stmos.read_file(p)
            self.STM.OS = content if ok else ""
            self.vars["STM.OS"] = self.STM.OS
            if not ok and self.dev_mode:
                yield {"t": "toast", "text": "stm.os read 失败：%s" % p}
            return

        if op == "create":
            ok, msg = stmos.create_file(p)
            if not ok and self.dev_mode:
                yield {"t": "toast", "text": "stm.os create：%s" % msg}
            return

        if op == "remove":
            ok, msg = stmos.remove_file(p)
            if not ok and self.dev_mode:
                yield {"t": "toast", "text": "stm.os remove：%s" % msg}
            return

        if op == "revision":
            ok, msg = stmos.revision_file(p, s.get("find"), s.get("replace"))
            if not ok and self.dev_mode:
                yield {"t": "toast", "text": "stm.os revision：%s" % msg}
            return

    # ------------------------------------------------------------------ #
    # 小工具
    # ------------------------------------------------------------------ #
    def _sprite_event(self, path, args, kwargs):
        """拆 S.character("图.png", pos="left", tag="kongjie")。

        立绘可以同时站好几张，靠 tag 认人、pos 决定站哪（left/center/right）。
        不写 tag 就用图片文件名当 tag。
        """
        pos = str(kwargs.get("pos") or (args[1] if len(args) > 1 else "center"))
        tag = kwargs.get("tag") or ""
        if not tag:
            base = os.path.basename(path.replace("\\", "/"))
            tag = os.path.splitext(base)[0]
        ev = {"t": "sprite", "path": self.resolve(path),
              "pos": pos.lower(), "tag": tag}
        # 逐张立绘的增强控制：只有写了才带上，没写就走默认值（老脚本行为不变）。
        # 剧本里写的是字面量，parser 给的是字符串，这里统一转成数字，免得渲染层再判断类型。
        def _num(v, cast):
            try:
                return cast(v)
            except (TypeError, ValueError):
                return None
        for key, cast in (("scale", float), ("alpha", int),
                          ("y", float), ("rotate", float)):
            if key in kwargs and kwargs[key] is not None:
                val = _num(kwargs[key], cast)
                if val is not None:
                    ev[key] = val
        if "expr" in kwargs:
            ev["expr"] = kwargs["expr"] or ""
        return [ev]

    def _say_text(self, raw):
        """台词默认是纯文本；带 + 号或 STM. 的才当算式求值。"""
        if "+" in raw or "STM." in raw:
            try:
                return str(self.eval_expr(raw))
            except STMFatal:
                pass
        return strip_quotes(raw)

    def _assign(self, name, value):
        if name.upper().startswith("STM."):
            setattr(self.STM, name.split(".", 1)[1], value)
            return
        self.vars[name] = value

    def _rand_draw(self, a, b):
        """回放感知随机：正常跑抽一枚记下，回放时吃记录原样返回。

        与 _take_answer 共用同一条有序回放流 self._replay：choose/question
        由 _take_answer 消费，rand 由本函数消费，二者按剧本里出现的顺序各取所需。
        老存档里没有 rand 项时，下一项必然不是 ("rand", ..)，于是退回「现场新抽」，
        不会越界吞噬 choose/question —— 旧存档依旧能正常重载（只是随机分支不再精确）。
        """
        a, b = int(a), int(b)
        if self._replay_i < len(self._replay):
            kind, val = self._replay[self._replay_i]
            if kind == "rand":
                self._replay_i += 1
                self.answers.append(("rand", val))
                return val
        val = random.randint(a, b)
        self.answers.append(("rand", val))
        return val

    def _take_answer(self):
        if self._replay_i < len(self._replay):
            kind, val = self._replay[self._replay_i]
            self._replay_i += 1
            self.answers.append((kind, val))
            return val
        return None
