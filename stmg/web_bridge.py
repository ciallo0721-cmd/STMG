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
"""

import json

from stmg import options as optmod
from stmg import parser
from stmg import stdlib_api
from stmg.runtime import Runtime


def _no_net(url="", key="", **kw):
    """网页里没有同步 socket，R.api 直接挡掉，免得整个剧本卡死。"""
    return False, "网页版不支持联网请求"


stdlib_api.call_api = _no_net


def _rel(path):
    """把引擎解析出来的虚拟路径还原成项目内的相对路径，前端好找素材。"""
    p = str(path or "").replace("\\", "/")
    i = p.find("/game/")
    if i >= 0:
        return p[i + 6:]
    return p


class Driver(object):
    def __init__(self, script_text, options_text=""):
        self.script = parser.parse_text(script_text, "/game/script.stm")
        try:
            self.opt = optmod.parse_options_text(options_text) if options_text else {}
        except Exception:                              # noqa: BLE001
            self.opt = {}
        self.rt = Runtime(self.script, self.opt, dev_mode=False)
        self.gen = self.rt.run()
        self.done = False

    # ------------------------------------------------------------------ #
    def next(self, answer=None):
        if self.done:
            return json.dumps({"t": "__done__"})
        try:
            ev = self.gen.send(answer)
        except StopIteration:
            self.done = True
            return json.dumps({"t": "__done__"})
        except Exception as e:                         # noqa: BLE001
            self.done = True
            return json.dumps({"t": "fatal",
                               "message": "%s: %s" % (type(e).__name__, e)})
        ev = dict(ev)
        if ev.get("path"):
            ev["path"] = _rel(ev["path"])
        return json.dumps(ev, ensure_ascii=False)

    # ------------------------------------------------------------------ #
    def info(self):
        """给前端的一点点元信息。"""
        return json.dumps({"title": self.script.title,
                           "w": self.script.width, "h": self.script.height,
                           "ver": self.script.header.get("ver", "1.0.0"),
                           "errors": self.script.error_count()},
                          ensure_ascii=False)
