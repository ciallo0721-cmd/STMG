# -*- coding: utf-8 -*-
"""Session —— 引擎的「推进器」。

把 Runtime 的事件流整理成「一个当前等待玩家的事件 + 已经发生的场景变化」，
渲染层只需要问 Session 三件事：现在显示什么、我点了以后变什么、存/读档怎么办。

不依赖 pygame，所以可以无头跑（`start.py --auto`）。
"""

import types

from .runtime import Runtime

# 这些事件只是「顺手改变画面/声音」，不用等玩家；其余的都是要停下等操作的。
# wait 故意**不**在里面：python 代码块逐行显示时，它要真的停够时间再往下走，
# 所以它和 say / choose 一样会变成当前 block，交给界面去等。
SIDE_EFFECTS = ("bg", "picture", "sprite", "bgm", "se", "voice",
                "stop", "hide", "toast", "python", "achieve",
                # 第 2 期新增的副作用型事件（T1 在回放时产出）：它们只是把联网 /
                # 文件操作的结果带回给界面与存档，不阻塞推进，必须登记进这里，
                # 否则回放时会卡在这两个事件上。
                "api_result", "os_result")

# 序列化时的占位哨兵：表示「这个值没法变成 JSON，整项跳过」。
_SKIP = object()


def _to_jsonable(v):
    """只保留 JSON 友好类型；其余（命名空间 / 模块 / 函数 / 类 / 对象）一律跳过。

    tuple 会转成 list（读回来是 list，剧情里用得到下标，可接受）；
    list / dict 里的非友好叶子直接丢掉，不强行塞 None 以免和「真没有」混淆。
    """
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (list, tuple)):
        return [_to_jsonable(x) for x in v if _to_jsonable(x) is not _SKIP]
    if isinstance(v, dict):
        out = {}
        for kk, x in v.items():
            jx = _to_jsonable(x)
            if jx is _SKIP:
                continue
            out[str(kk)] = jx
        return out
    return _SKIP


def _scene_copy(scene):
    """把当前画面状态拷贝一份，避免存进去的快照被后来的推进改坏。"""
    if not isinstance(scene, dict):
        return {"bg": "", "picture": "", "sprites": {}, "bgm": "", "bgm_loop": True}
    return {
        "bg": scene.get("bg", ""),
        "picture": scene.get("picture", ""),
        "sprites": {tag: dict(sp) for tag, sp in scene.get("sprites", {}).items()},
        "bgm": scene.get("bgm", ""),
        "bgm_loop": scene.get("bgm_loop", True),
    }


class Session(object):
    def __init__(self, script, options=None, dev_mode=True):
        self.script = script
        self.options = options
        self.dev_mode = dev_mode
        self.reset()

    # ------------------------------------------------------------------ #
    def reset(self, replay=None, target_say=0):
        self.runtime = Runtime(self.script, self.options, self.dev_mode)
        # 读档重放：这段路上已经看过的提示不用再演一遍，尤其 python 代码块
        # 那几秒等待——不静音的话会在重放中途停下来卡住，读档就废了。
        # 注意代码本身照跑，它算出来的变量后面还要用。
        self.runtime.quiet = bool(target_say)
        self.gen = self.runtime.run(replay=replay)
        # sprites 是个字典：tag -> {"path":..., "pos": "left"/"center"/"right"}
        # 同时可以站好几张立绘，跟 Ren'Py 的 show 一个意思。
        self.scene = {"bg": "", "picture": "", "sprites": {},
                      "bgm": "", "bgm_loop": True}
        self.block = None
        self.effects = []        # 本次推进中产生的场景/音频指令
        self.toasts = []         # 本次推进中的右上角提示
        self.say_count = 0
        self.finished = False
        self.crashed = False
        self.lang = ""        # 当前语言版本（多语言剧本用，空 = 默认 script.stm）

        while True:
            blk = self._pull()
            if blk["t"] == "say" and self.say_count < target_say:
                continue
            if blk["t"] == "wait" and self.say_count < target_say:
                # 兜底：万一还有 wait 漏出来，重放时也别停在它上面
                continue
            break
        self.runtime.quiet = False
        self.block = blk
        return blk

    # ------------------------------------------------------------------ #
    def _raw(self):
        if self.finished:
            return {"t": "end"}
        try:
            ev = next(self.gen)
        except StopIteration:
            self.finished = True
            return {"t": "end"}
        return ev

    def _pull(self, first=None):
        """吃掉落幕之间的副作用事件，停在下一个「要让玩家动一下」的事件上。

        first：send() 的返回值。gen.send(v) 会把下一个事件直接返回，不接住就丢了，
               表现为「玩家回答完，紧跟着的那一句台词凭空消失」。
        """
        pending = first
        while True:
            if pending is not None:
                ev, pending = pending, None
            else:
                ev = self._raw()
            t = ev["t"]
            if t in SIDE_EFFECTS:
                self._apply(ev)
                continue
            if t == "say":
                self.say_count += 1
            if t in ("end", "fatal"):
                self.finished = True
                self.crashed = (t == "fatal")
            return ev

    def _apply(self, ev):
        t = ev["t"]
        if t == "bg":
            self.scene["bg"] = ev.get("path", "")
            if ev.get("clear"):
                # 和 Ren'Py 的 scene 一样：换背景顺带清场
                self.scene["sprites"].clear()
        elif t == "picture":
            self.scene["picture"] = ev.get("path", "")
        elif t == "sprite":
            tag = ev.get("tag") or "_"
            if ev.get("path"):
                self.scene["sprites"][tag] = {
                    "path": ev["path"],
                    "pos": ev.get("pos", "center"),
                    "scale": ev.get("scale"),
                    "alpha": ev.get("alpha"),
                    "y": ev.get("y"),
                    "expr": ev.get("expr"),
                    "rotate": ev.get("rotate"),
                }
            else:
                self.scene["sprites"].pop(tag, None)
        elif t == "bgm":
            self.scene["bgm"] = ev.get("path", "")
            self.scene["bgm_loop"] = ev.get("loop", True)
        elif t == "stop":
            what = ev.get("what", "bgm")
            if what in ("bgm", "all"):
                self.scene["bgm"] = ""
        elif t == "hide":
            what = ev.get("what", "sprite")
            if what in ("sprite", "all"):
                self.scene["sprites"].clear()
            if what in ("picture", "all"):
                self.scene["picture"] = ""
            if what not in ("sprite", "all", "picture"):
                self.scene["sprites"].pop(what, None)   # 按 tag 隐藏单个立绘
        elif t == "toast":
            self.toasts.append(ev.get("text", ""))
        elif t in ("api_result", "os_result"):
            # 联网 / 文件操作的回放结果：只是把结果交回界面与存档，不改动画面
            pass
        self.effects.append(ev)

    # ------------------------------------------------------------------ #
    # 推进
    # ------------------------------------------------------------------ #
    def next_block(self):
        """当前是 say，玩家点了一下，继续。"""
        self.effects = []
        self.toasts = []
        self.block = self._pull()
        return self.block

    def answer(self, value):
        """当前是 choose / question，把玩家给的回答塞回引擎。"""
        self.effects = []
        self.toasts = []
        try:
            first = self.gen.send(value)
        except StopIteration:
            self.finished = True
            self.block = {"t": "end"}
            return self.block
        self.block = self._pull(first)
        return self.block

    # ------------------------------------------------------------------ #
    # 存档
    # ------------------------------------------------------------------ #
    def snapshot(self):
        """生成 v2 状态快照（纯 JSON，ensure_ascii=False 由 save.write_slot 负责）。

        相比老存档新增：
            format    固定 2，老存档没有 / 为 1 走原路径
            chosen    已经选过的选项（快照）
            vars      变量快照（只留 JSON 友好类型，跳过 STM/R 命名空间与模块对象）
            scene     存档瞬间的画面（立绘 / 背景 / BGM），读档时先灌进来让画面立刻正确
            lang      该档所用语言版本，空 = 默认
        """
        rt = self.runtime
        raw_vars = {}
        for k, v in rt.vars.items():
            # STM / R 是运行时命名空间，不能序列化；非字符串键也跳过
            if k in ("STM", "R") or not isinstance(k, str):
                continue
            jv = _to_jsonable(v)
            if jv is _SKIP:
                continue
            raw_vars[k] = jv
        return {
            "format": 2,
            "script": self.script.path,
            "title": self.script.title,
            "answers": list(rt.answers),
            "say_count": self.say_count,
            "history_tail": rt.history[-3:],
            "chosen": sorted(rt.chosen),
            "vars": raw_vars,
            "scene": _scene_copy(self.scene),
            "lang": getattr(self, "lang", ""),
        }

    def restore(self, snap):
        """读档恢复。

        双轨恢复（快照 + 重放一起用，不是二选一）：
          1) 先 reset(replay=answers, target_say=say_count) 重放到存档点，
             把「执行位置」对上，玩家才从这个断点继续；
          2) 重放结束后再用快照的 scene / vars / chosen / lang 覆盖——
             快照比重放结果更权威（重放只为了让执行位置对上，有些副作用
             比如画面细节未必能完全由重放重建）。

        老存档（无 format 或 format=1）走原路径，行为完全不变。
        """
        answers = snap.get("answers") or []
        target = int(snap.get("say_count", 0))
        if int(snap.get("format", 1)) >= 2:
            self.reset(replay=answers, target_say=target)
            self._apply_snapshot(snap)
        else:
            # 老存档：原路径，行为完全不变
            self.reset(replay=answers, target_say=target)

    def _apply_snapshot(self, snap):
        """把快照里更权威的画面 / 变量 / 已选状态覆写回当前运行态。

        注意：STM / R 这两个命名空间是 reset 时重建的，快照里没有也不该覆盖，
        否则会把运行时对象丢掉；变量快照只含用户变量，正好对得上。
        """
        rt = self.runtime
        # 1) 画面：用存档瞬间的画面覆盖重放重建的画面
        saved_scene = snap.get("scene")
        if isinstance(saved_scene, dict):
            for key in ("bg", "picture", "bgm", "bgm_loop"):
                if key in saved_scene:
                    self.scene[key] = saved_scene[key]
            if isinstance(saved_scene.get("sprites"), dict):
                self.scene["sprites"] = {
                    tag: dict(sp) for tag, sp in saved_scene["sprites"].items()}
        # 2) 变量：快照比重放结果更权威，整批覆盖（STM/R 不在快照里，自然保留）
        saved_vars = snap.get("vars")
        if isinstance(saved_vars, dict):
            for k, v in saved_vars.items():
                rt.vars[str(k)] = v
        # 3) 已选选项
        saved_chosen = snap.get("chosen")
        if isinstance(saved_chosen, (list, tuple)):
            rt.chosen = set(saved_chosen)
        # 4) 语言版本
        self.lang = snap.get("lang", "") or ""

    @property
    def text(self):
        """当前这一句要显示的文本（可能带 md 标记）。"""
        if self.block:
            if self.block["t"] == "say":
                return self.block.get("text", "")
            if self.block["t"] == "wait" and self.runtime.history:
                # python 代码块在等下一行提示：对话框继续保持上一句，别突然空掉
                return self.runtime.history[-1][1]
        return ""

    @property
    def speaker(self):
        if self.block:
            if self.block["t"] == "say":
                return self.block.get("who")
            if self.block["t"] == "wait" and self.runtime.history:
                return self.runtime.history[-1][0] or None
        return None
