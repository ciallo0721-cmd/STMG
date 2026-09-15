#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""美化包发布器 —— 把 mod/<名字>/ 打包成「XXX_美化包」。

    python tools/modpub.py example_sakura
    python tools/modpub.py 樱花飘落 --out D:/分享
    python tools/modpub.py example_sakura --no-zip

产物（默认 dist/mods/）：

    樱花飘落_美化包/
    ├── 安装说明.md              ← 第一行就写明「这是美化包，不是 STMG 本体」
    ├── 校验报告.txt             查过什么、有没有警告，都记下来
    └── example_sakura/          ← 这一层丢进 mod/ 就能用
        ├── mod.json
        ├── gui.py
        ├── theme.css
        └── theme.js
    樱花飘落_美化包.zip           ← 上面那个目录的压缩包

⚠️ 这个工具**只发美化包**，永远不含引擎（stmg/）、剧本、启动器和任何
   可执行文件。想发布游戏本体请用 `stmenc/start.py`（打包发布）或
   `tools/htmlpub.py`（发布为 HTML）——那是另外两件事，别混。

有 error 级别的违规就直接拒绝打包，不给 --force 后门。
"""

import os
import shutil
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from stmg import mod                                         # noqa: E402

BANNER = """# {name} —— STMG 美化包

> **这是 STMG 的「美化包」（外观主题），不是 STMG 本体。**
> 它里面没有引擎、没有剧本、没有启动器，只有界面样式 —— 装上去只是换了
> 个样子，不会给谁的游戏多加一个功能。想发布游戏本体请用 STMG 自带的
> `stmenc/start.py`（打包发布）或 `tools/htmlpub.py`（发布为 HTML）。

- 包名：{name}（目录名 `{mid}`）
- 版本：{version}
- 作者：{author}
- 说明：{desc}
- 打包时间：{when}
- 引擎要求：STMG {engine}

## 怎么装

1. 把 `{mid}/` 这个文件夹整个拷进 STMG 的 `mod/` 目录里
2. 打开 `mod/active.json`，把里面的 `"mod"` 改成 `{mid}`
3. 启动游戏，外观就变了

不想动配置文件也行，跑游戏时临时指定：

```
python start.py script.stm --mod {mid}
```

或者用启动器：点「美化包」→ 选中它 → 启用。

## 怎么卸

把 `"mod"` 改回 `none`，或者直接删掉 `mod/{mid}/`。
一个美化包的所有改动都在它自己的文件夹里，删干净就回到原样。

## 它不能做什么

按 STMG 的规矩，美化包是**主题**不是**补丁**，所以：

- 不能改引擎行为（想改请去改 `stmg/` 源码，那是你自己的 fork）
- 不能带可执行文件、不能联网、不能碰玩家存档
- 只能声明外观：`gui.py` 里一个 CONFIG 字典 + `theme.css` / `theme.js`

这份包发布前跑过 `tools/modcheck.py` 的静态检查，报告见 `校验报告.txt`。
"""


def banner_for(man, mid, issues):
    return BANNER.format(
        name=man.get("name") or mid,
        mid=mid,
        version=man.get("version") or "1.0.0",
        author=man.get("author") or "匿名",
        desc=man.get("desc") or "（作者没写说明）",
        engine=str(man.get("engine") or ">=1.0.0"),
        when=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def report_for(mid, man, issues, files):
    lines = ["STMG 美化包校验报告",
             "美化包：%s（%s）" % (man.get("name") or mid, mid),
             "检查时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"),
             "检查工具：tools/modcheck.py", "",
             "检查项：", 
             "  1. .py 里只能声明 CONFIG 字典，不许有可执行代码",
             "  2. 不许带引擎本体 / 工具链 / 可执行文件",
             "  3. 样式与脚本不许联网、不许碰存档",
             ""]
    errs = mod.errors_of(issues)
    warns = mod.warnings_of(issues)
    lines.append("结果：%s" % ("有 %d 个错误（不该走到这一步）" % len(errs) if errs
                              else "通过"))
    for m in warns:
        lines.append("  提示：%s" % m)
    lines.append("")
    lines.append("包含的文件（%d 个）：" % len(files))
    for f in files:
        lines.append("  %s" % f)
    return "\n".join(lines) + "\n"


def collect_files(path):
    out = []
    for dirpath, _dirs, files in os.walk(path):
        for fn in sorted(files):
            full = os.path.join(dirpath, fn)
            out.append(os.path.relpath(full, path).replace("\\", "/"))
    return sorted(out)


def safe_name(s):
    s = "".join(c for c in str(s) if c not in '\\/:*?"<>|').strip()
    return s or "美化包"


def main(argv):
    args = argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if args else 2

    src = args[0]
    out_root = None
    do_zip = True
    i = 1
    while i < len(args):
        if args[i] == "--out":
            i += 1
            out_root = args[i]
        elif args[i] == "--no-zip":
            do_zip = False
        elif args[i] == "--zip":
            do_zip = True
        i += 1

    path = mod.find_mod(src)
    if not path and os.path.isdir(src) and os.path.isfile(os.path.join(src, mod.MANIFEST_NAME)):
        path = os.path.abspath(src)
    if not path:
        print("找不到美化包：%s（跑 python tools/modcheck.py 看看有哪些）" % src)
        return 1

    mid = os.path.basename(path)
    man = mod.manifest(path)
    print("美化包：%s（%s）" % (man.get("name") or mid, mid))
    print("路径　：%s" % path)
    print("-" * 62)

    # ---------- 1. 先严格校验，不合格直接拒 ----------
    issues = mod.verify(path)
    errs = mod.errors_of(issues)
    warns = mod.warnings_of(issues)
    for m in warns:
        print("  [提示] %s" % m)
    if errs:
        for m in errs:
            print("  [错误] %s" % m)
        print("-" * 62)
        print("拒绝打包：有 %d 个错误。美化包不许改引擎、不许带可执行文件、"
              "不许联网碰存档。" % len(errs))
        print("如果是想改引擎行为，请直接改 stmg/ 里的源码，那是引擎该改的地方。")
        return 1

    # ---------- 2. 拷进 dist/mods/xxx_美化包/ ----------
    name = safe_name(man.get("name") or mid)
    out_root = os.path.abspath(out_root or os.path.join(ROOT, "dist", "mods"))
    out = os.path.join(out_root, "%s_美化包" % name)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)

    dst = os.path.join(out, mid)
    shutil.copytree(path, dst)

    files = collect_files(path)
    with open(os.path.join(out, "安装说明.md"), "w", encoding="utf-8") as f:
        f.write(banner_for(man, mid, issues))
    with open(os.path.join(out, "校验报告.txt"), "w", encoding="utf-8") as f:
        f.write(report_for(mid, man, issues, files))

    made = ["安装说明.md", "校验报告.txt", "%s/" % mid]

    # ---------- 3. 顺手打个 zip ----------
    zip_path = ""
    if do_zip:
        zip_path = os.path.join(out_root, "%s_美化包.zip" % name)
        if os.path.exists(zip_path):
            os.remove(zip_path)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in ["安装说明.md", "校验报告.txt"] + ["%s/%s" % (mid, r) for r in files]:
                z.write(os.path.join(out, rel.replace("/", os.sep)), rel)

    # ---------- 4. 汇报 ----------
    print("检查通过：没有错误，%d 条提示。" % len(warns))
    print("-" * 62)
    print("产物目录：%s" % out)
    for m in made:
        print("    %s" % m)
    if zip_path:
        print("压缩包　：%s（%.1f KB）"
              % (zip_path, os.path.getsize(zip_path) / 1024.0))
    print("-" * 62)
    print("发布的是「美化包」，不是 STMG 本体：")
    print("  · 里面没有引擎（stmg/）、没有剧本、没有启动器")
    print("  · 拿到它的人只是换了个外观，不会多出任何功能")
    print("  · 想发布游戏本体请用 stmenc/start.py 或 tools/htmlpub.py")
    print("安装方式：把 %s/ 丢进 STMG 的 mod/ 目录，再把 active.json 里的 "
          "\"mod\" 改成 %s" % (mid, mid))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
