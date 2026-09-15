#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""语法检查器：不开窗口，只把剧本从头到尾体检一遍。

    python tools/check.py demo
    python tools/check.py demo/script.stm
    python tools/check.py demo --verbose     把语句树也打出来
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from stmg import options as optmod, parser                     # noqa: E402
from stmg.errors import level_name                             # noqa: E402


def find_script(target):
    if os.path.isfile(target):
        return target
    for name in ("script.stm", "script.stmdec"):
        p = os.path.join(target, name)
        if os.path.isfile(p):
            return p
    return ""


def main(argv):
    args = argv[1:]
    verbose = "--verbose" in args
    args = [a for a in args if not a.startswith("--")]
    target = os.path.abspath(args[0] if args else os.path.join(ROOT, "demo"))

    path = find_script(target)
    if not path:
        print("没找到 script.stm：%s" % target)
        return 2

    sc = parser.parse_file(path)
    game_dir = os.path.dirname(path)

    print("=" * 64)
    print("剧本：%s" % path)
    print("标题：%s" % sc.title)
    print("分辨率：%dx%d    字体：%s    版本：%s"
          % (sc.width, sc.height, sc.font, sc.header.get("ver", "?")))
    print("=" * 64)

    if verbose:
        from start import summarize
        summarize(sc)
        print("-" * 64)

    # 统计
    says = [s for s in sc.walk() if s["k"] == "say"]
    chooses = [s for s in sc.walk() if s["k"] == "choose"]
    calls = [s for s in sc.walk() if s["k"] == "call"]
    print("台词/旁白 %d 句 · 选择支 %d 处 · 引擎调用 %d 次"
          % (len(says), len(chooses), len(calls)))

    pys = [s for s in sc.walk() if s["k"] == "pycode"]
    if pys:
        print("python 代码块 %d 处（开发模式专属：发布版会整块跳过）" % len(pys))

    # 素材存在性
    ASSET_METHODS = {"cg", "bg", "background", "picture", "play",
                     "sound", "voice"}
    missing = []
    for s in sc.walk():
        paths = []
        if s.get("path"):
            paths.append(s["path"])
        if s["k"] == "call" and s["obj"].upper() == "S" \
                and s["method"].lower() in ASSET_METHODS and s["args"]:
            paths.append(s["args"][0])
        for p in paths:
            if p and not os.path.isfile(os.path.join(game_dir, p)):
                missing.append((s["line"], p))
    if missing:
        print("\n素材还没放（游戏里会自动画占位块，不影响跑）：")
        for line, p in missing[:12]:
            print("  行 %s  %s" % (line, p))
        if len(missing) > 12:
            print("  ... 还有 %d 个" % (len(missing) - 12))

    # options
    op = optmod.load_options(optmod.find_options(path))
    if not op.get("enc"):
        print("\n提醒：options.stm 里还没写 Enc（加密口令），发布时会用不了。")
    for i in op.get("_issues", []):
        print(" options: %s" % i)

    print("-" * 64)
    if not sc.issues:
        print("语法检查通过，没有发现问题。")
        return 0
    for i in sc.issues:
        print("%s  %s" % ("错误" if i.level == "error" else "提示", i))
    n = sc.error_count()
    if n:
        print("\n共 %d 个错误 -> %s" % (n, level_name(n)))
        return 1
    print("\n没有错误，只有提示。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
