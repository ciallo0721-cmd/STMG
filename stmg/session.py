# -*- coding: utf-8 -*-
"""Session —— 引擎的「推进器」。

把 Runtime 的事件流整理成「一个当前等待玩家的事件 + 已经发生的场景变化」，
渲染层只需要问 Session 三件事：现在显示什么、我点了以后变什么、存/读档怎么办。

不依赖 pygame，所以可以无头跑（`start.py --auto`）。
"""

from .runtime import Runtime

# 这些事件只是「顺手改变画面/声音」，不用等玩家；其余的都是要停下等操作的
SIDE_EFFECTS = ("bg", "picture", "sprite", "bgm", "se", "voice",
                "stop", "hide", "toast", "python")


class Session(object):
    def __init__(self, script, options=None, dev_mode=True):
        self.script = script
        self.options = options
        self.dev_mode = dev_mode
        self.reset()

    # ------------------------------------------------------------------ #
    def reset(self, replay=None, target_say=0):
        self.runtime = Runtime(self.script, self.options, self.dev_mode)
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

        while True:
            blk = self._pull()
            if blk["t"] == "say" and self.say_count < target_say:
                continue
            break
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
                self.scene["sprites"][tag] = {"path": ev["path"],
                                              "pos": ev.get("pos", "center")}
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
        return {
            "script": self.script.path,
            "title": self.script.title,
            "answers": list(self.runtime.answers),
            "say_count": self.say_count,
            "history_tail": self.runtime.history[-3:],
        }

    def restore(self, snap):
        self.reset(replay=snap.get("answers") or [],
                   target_say=int(snap.get("say_count", 0)))

    @property
    def text(self):
        """当前这一句要显示的文本（可能带 md 标记）。"""
        if self.block and self.block["t"] == "say":
            return self.block.get("text", "")
        return ""

    @property
    def speaker(self):
        if self.block and self.block["t"] == "say":
            return self.block.get("who")
        return None
