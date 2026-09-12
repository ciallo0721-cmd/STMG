#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""STMG 开发启动器。

  python start.py                      跑 demo/script.stm
  python start.py demo/script.stm      跑指定剧本
  python start.py --check 剧本         只做语法检查，不开窗口
  python start.py --auto 剧本          无头跑一遍（自动选第一个选项），打印全部台词
  python start.py --auto=2 剧本        自动选第三个选项
  python start.py --release 剧本       用发布版规则跑（禁 STM.python、关联网）
  python start.py 剧本.stmdec --key 口令   跑加密剧本

改完剧本用 --check 先过一遍，再开窗口看效果。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from stmg import crypto, options as optmod, parser            # noqa: E402
from stmg.errors import level_name                            # noqa: E402
from stmg.session import Session                              # noqa: E402

DEFAULT_SCRIPT = os.path.join(HERE, "demo", "script.stm")


def load_script(path, key=None):
    if path.lower().endswith(".stmdec") or crypto.is_encrypted(path):
        text = crypto.load_text(path, key)
        return parser.parse_text(text, path)
    return parser.parse_file(path)


def print_issues(sc):
    if not sc.issues:
        print("语法检查通过，没有发现问题。")
        return 0
    for i in sc.issues:
        print("  %s  %s" % ("错误" if i.level == "error" else "提示", i))
    n = sc.error_count()
    if n:
        print("\n共 %d 个错误 -> %s" % (n, level_name(n)))
        return 1
    print("\n没有错误，只有 %d 条提示。" % len(sc.issues))
    return 0


def summarize(sc, stmts=None, depth=0):
    for s in (sc.body if stmts is None else stmts):
        pad = "  " * depth
        k = s["k"]
        if k == "say":
            from stmg.markdown import strip_quotes
            who = (s["who"] + " ") if s["who"] else ""
            print("%s%-10s %s「%s」" % (pad, "say", who, strip_quotes(s["text"])[:34]))
        elif k == "choose":
            print("%s%-10s %s" % (pad, "choose", " / ".join(s["options"])))
        elif k == "if":
            print("%s%-10s %s" % (pad, "if", s["cond"]))
            summarize(sc, s["body"], depth + 1)
            if s.get("else_body"):
                print("%s%-10s" % (pad, "else"))
                summarize(sc, s["else_body"], depth + 1)
        elif k == "question":
            print("%s%-10s %s" % (pad, "question", s["prompt"]))
        elif k == "set":
            print("%s%-10s %s = %s" % (pad, "set", s["name"], s["expr"]))
        elif k == "define":
            print("%s%-10s %s" % (pad, "character", s["name"]))
        elif k == "sprite":
            print("%s%-10s %s" % (pad, "sprite", s["path"]))
        elif k == "call":
            extra = ["%s=%s" % kv for kv in s["kwargs"].items()]
            print("%s%-10s %s.%s(%s)" % (pad, "call", s["obj"], s["method"],
                                         ", ".join(list(s["args"]) + extra)))
        elif k == "label":
            print("%s%-10s %s" % (pad, "label", s["name"]))


def run_auto(script, options, pick=0, dev_mode=True):
    """无头推进，把事件流全打出来。"""
    sess = Session(script, options, dev_mode)
    steps = 0
    while True:
        blk = sess.block
        t = blk["t"]
        for ev in sess.effects:
            print("        [%s] %s" % (ev["t"], ev.get("path") or ev.get("what")
                                       or ev.get("text") or ""))
        if t == "say":
            who = (blk.get("who") + "：") if blk.get("who") else ""
            print("%s%s" % (who, blk.get("text", "")))
            sess.next_block()
        elif t == "choose":
            opts = blk["options"]
            idx = min(pick, len(opts) - 1) if opts else 0
            print("  >>> 选择：[%s]" % opts[idx])
            sess.answer(opts[idx])
        elif t == "question":
            print("  >>> 询问：%s -> 自动回答「测试」" % blk.get("prompt"))
            sess.answer("测试")
        elif t == "fatal":
            print("\n!! 运行出错：" + blk.get("message", ""))
            if blk.get("trace"):
                print(blk["trace"])
            return 1
        else:
            print("\n—— 剧本结束，共推进 %d 步 ——" % steps)
            return 0
        steps += 1
        if steps > 5000:
            print("!! 推进超过 5000 步，可能是 S.jump 死循环")
            return 1


def main(argv):
    args = [a for a in argv[1:]]
    mode = "gui"
    key = None
    pick = 0
    dev_mode = True
    path = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--check":
            mode = "check"
        elif a == "--auto":
            mode = "auto"
        elif a.startswith("--auto="):
            mode, pick = "auto", int(a.split("=", 1)[1])
        elif a == "--release":
            dev_mode = False
        elif a == "--key":
            i += 1
            key = args[i]
        elif a.startswith("--"):
            print("不认识的参数：%s" % a)
            return 2
        else:
            path = a
        i += 1

    path = path or DEFAULT_SCRIPT
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        print("找不到剧本文件：%s" % path)
        return 2

    try:
        script = load_script(path, key)
    except crypto.DecryptError as e:
        print("解密失败：%s" % e)
        return 3

    options = optmod.load_options(optmod.find_options(path), key)

    if mode == "check":
        print("剧本：%s" % path)
        print("标题：%s   分辨率：%dx%d   字体：%s"
              % (script.title, script.width, script.height, script.font))
        print("-" * 60)
        summarize(script)
        print("-" * 60)
        return print_issues(script)

    if mode == "auto":
        return run_auto(script, options, pick, dev_mode)

    if script.error_count():
        print("剧本有 %d 个错误，先修好再开窗口：" % script.error_count())
        print_issues(script)
        return 1

    from stmg.gui import App
    App(script, options, dev_mode).run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
