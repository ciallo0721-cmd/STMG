#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""美化包检查器。

    python tools/modcheck.py                    列出所有美化包 + 当前启用哪个
    python tools/modcheck.py example_sakura     详细检查一个包
    python tools/modcheck.py mod/example_sakura 也可以直接给路径
    python tools/modcheck.py --use example_sakura   启用某个包
    python tools/modcheck.py --new 我的主题      生成新包骨架
    python tools/modcheck.py --all               把所有包都详细检查一遍

检查什么：见 mod/README.md 的「三条硬性限制」。简单说——
美化包只能声明外观，不许有可执行代码、不许带引擎和可执行文件、不许联网碰存档。

有 error 就返回 1，方便接到 CI 或启动器里。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from stmg import mod                                         # noqa: E402


def find_any(arg):
    """参数可以是 id、也可以是路径。"""
    p = mod.find_mod(arg)
    if p:
        return p
    cand = os.path.abspath(arg)
    if os.path.isdir(cand) and os.path.isfile(os.path.join(cand, mod.MANIFEST_NAME)):
        return cand
    return None


def print_report(path, verbose=True):
    """打印一个包的检查结果，返回 error 条数。"""
    m = mod.manifest(path)
    title = m.get("name") or os.path.basename(path)
    print("=" * 62)
    print("美化包：%s（%s）" % (title, os.path.basename(path)))
    print("路径　：%s" % path)
    if m:
        print("版本　：%s    作者：%s" % (m.get("version", "?"), m.get("author", "?")))
        if m.get("desc"):
            print("说明　：%s" % m["desc"])

    issues = mod.verify(path)
    errs = [x for x in issues if x[0] == "error"]
    warns = [x for x in issues if x[0] == "warn"]

    if not errs and not warns:
        print("\n检查通过：没有问题。")
    for lv, msg in errs:
        print("\n  [错误] %s" % msg)
    for lv, msg in warns:
        print("\n  [提示] %s" % msg)
    if errs:
        print("\n不合格：%d 个错误。修好才能发布。" % len(errs))
    elif warns:
        print("\n可以用，但有 %d 条提示。" % len(warns))
    return len(errs)


def list_all():
    packs = mod.list_mods()
    active = mod.active_id()
    print("美化包目录：%s" % mod.find_dir())
    print("当前启用　：%s" % active)
    print("-" * 62)
    if not packs:
        print("（还没有任何美化包）")
        return 1
    bad = 0
    for p in packs:
        mark = "*" if p["id"] == active else " "
        issues = mod.verify(p["path"])
        errs = mod.errors_of(issues)
        tag = "正常" if not errs else "不合格（%d 个错误）" % len(errs)
        bad += 1 if errs else 0
        print("%s %-18s %-12s v%-8s %-14s %s"
              % (mark, p["id"], p["name"][:12], p["version"], p["author"][:14], tag))
        if errs and p["id"] == active:
            print("      ↑ 有问题，引擎会安全回退到原生外观：%s" % errs[0])
    print("-" * 62)
    print("* = 当前启用；用 --use <id> 切换，--new <名字> 新建，<id> 看详情。")
    return 1 if bad else 0


def main(argv):
    args = argv[1:]
    if not args:
        return list_all()

    a = args[0]
    if a in ("-h", "--help"):
        print(__doc__)
        return 0

    if a == "--new":
        if len(args) < 2:
            print("用法：python tools/modcheck.py --new 我的主题")
            return 2
        name = args[1]
        author = args[3] if len(args) > 3 and args[2] == "--author" else None
        try:
            path = mod.create_mod(ROOT, name, name=name, author=author)
        except OSError as e:
            print("新建失败：%s" % e)
            return 1
        print("已生成美化包骨架：%s" % path)
        print("里面那份 gui.py 只有 CONFIG 字典能改，注释里列了常用项。")
        print("改完跑一次：python tools/modcheck.py %s" % os.path.basename(path))
        return 0

    if a == "--use":
        if len(args) < 2:
            print("用法：python tools/modcheck.py --use 美化包名")
            return 2
        mid = args[1]
        if not mod.find_mod(mid):
            print("找不到美化包：%s" % mid)
            return 1
        issues = mod.verify(mod.find_mod(mid))
        errs = mod.errors_of(issues)
        if errs:
            print("这个包不合格，先修好再启用：%s" % errs[0])
            return 1
        print("已启用：%s（写进 %s）" % (mid, mod.set_active(mid)))
        return 0

    if a == "--list":
        return list_all()

    if a == "--all":
        codes = []
        for p in mod.list_mods():
            codes.append(print_report(p["path"]))
            print()
        return 1 if any(codes) else 0

    path = find_any(a)
    if not path:
        print("找不到美化包：%s（跑 python tools/modcheck.py 看看有哪些）" % a)
        return 1
    return 1 if print_report(path) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
