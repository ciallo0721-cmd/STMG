#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""语法检查器：不开窗口，只把剧本从头到尾体检一遍。

本工具只做「静态体检」——读剧本、解析、统计、查素材、查 options，
全程不启动 pygame、不开任何窗口，因此在 CI 或没有显示环境的服务器上也能跑。

核心价值：
  * 把 parser 阶段收集到的语法 Issue（错误 + 提示）全部打出来；
  * 统计台词 / 选择支 / 引擎调用 / Python 代码块的数量，便于体检剧本规模；
  * 顺手检查剧本里引用的素材文件是否真的躺在磁盘上（缺了游戏里只是画占位块，
    不影响运行，只提示）；
  * 提示 options.stm 里有没有写加密口令 Enc（发布必须，否则发布器用不了）。

退出码（给 shell / CI 当返回值用）：
  0  没有 error 级别问题（可能有「提示」，但提示不阻塞发布）
  1  有 error 级别问题，需要先修
  2  连 script.stm 都没找到（target 路径不对）

用法：
    python tools/check.py demo
    python tools/check.py demo/script.stm
    python tools/check.py demo --verbose     把语句树也打出来
"""

import os
import sys

# 英文 Windows（比如 CI 的 windows-latest）控制台编码是 cp1252，
# 一 print 中文（"剧本：xxx"）就抛 UnicodeEncodeError，把体检脚本自己先弄死。
# 这里把输出切到 UTF-8；终端不认就用替换字符兜着，至少结论能正常打出来。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from stmg import options as optmod, parser                     # noqa: E402
from stmg.errors import level_name                             # noqa: E402


def find_script(target):
    """把用户给的「目标」解析成 script.stm 文件的具体路径。

    参数 target 可能是两种东西：
      * 已经是剧本文件（如 demo/script.stm）-> 直接返回它自己；
      * 是目录（如 demo）-> 在该目录里依次找 script.stm、script.stmdec，
        找到哪个返回哪个（优先 .stm）；
    返回：脚本文件的路径字符串；如果两种都不是，返回空串 ""，
          调用方（main）据此打印「没找到」并以退出码 2 收场。
    删了会怎样：main 没法定位文件，整个 check 直接失败。
    """
    if os.path.isfile(target):
        return target
    for name in ("script.stm", "script.stmdec"):
        p = os.path.join(target, name)
        if os.path.isfile(p):
            return p
    return ""


def main(argv):
    """check.py 的命令行入口：解析参数 -> 体检剧本 -> 打印报告 -> 返回退出码。

    参数 argv：sys.argv（含程序名），例如 ["tools/check.py", "demo", "--verbose"]。
    主要流程：
      1. 解析 --verbose 开关，其余不以 -- 开头的参数当作 target；
      2. 用 find_script 定位脚本文件，找不到就打印提示并返回 2；
      3. parser.parse_file 解析整份剧本，拿到语句树 sc；
      4. 打印表头（标题 / 分辨率 / 字体 / 版本）与统计（台词 / 选择 / 调用 / py 块）；
      5. 遍历语句树，列出磁盘上缺失的素材文件（仅提示，不致命）；
      6. 加载 options.stm，提示缺 Enc 口令、打印 options 自身的 issue；
      7. 汇总 sc.issues：有 error 返回 1，否则返回 0。
    被谁调用：文件末尾 `if __name__ == "__main__"` 里 sys.exit(main(sys.argv))。
    """
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

    # 素材存在性：下面这些 S.* 调用，第一个实参是「磁盘上的素材文件路径」，
    # 需要确认它真的存在。缺了不会让游戏崩（运行时自动画占位块），
    # 但这里提前报出来，方便作者把美术资源放齐。
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
