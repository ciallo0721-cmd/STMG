#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把制作器构建产物同步到 docs/，供 GitHub Pages 直接托管。

GitHub Pages 有两条路可走：
  1. Settings → Pages → Source 选「Deploy from a branch」，分支 main、目录 /docs
  2. 自己 push 一个 gh-pages 分支 —— 那样主仓库干净，但每次更新要切分支

这里用第 1 条：产物直接进 main 的 docs/，push 完自动重新部署，
不用额外记任何命令。

用法：
    python tools/build_maker.py     # 先构建
    python tools/publish_pages.py   # 再同步并告诉你 git 该提交什么

注意：
  - docs/ 下的内容**全部是生成物**，不要在里面手改，重跑会覆盖。
  - Python 源文件本身跑不了，所以产物里没有 .py；docs/ 只放浏览器能吃的
    html/css/js/wasm/zip。
  - 启动器（serve.ps1、启动制作器.bat）只对本地解压有用，线上不需要，
    放上去反而让人误点下载，直接跳过。
"""

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "dist", "maker")
DST = os.path.join(ROOT, "docs")

# 这些只对“解压到本地双击启动”有意义，网页版不需要
SKIP_FILES = {"serve.ps1", "启动制作器.bat", "README.md"}


def main():
    if not os.path.isfile(os.path.join(SRC, "index.html")):
        print("!! 找不到 dist/maker/index.html —— 先跑 python tools/build_maker.py")
        return 1

    if os.path.isdir(DST):
        shutil.rmtree(DST)
    os.makedirs(DST)

    n = 0
    total = 0
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            if fn in SKIP_FILES:
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, SRC)
            out = os.path.join(DST, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copy2(full, out)
            n += 1
            total += os.path.getsize(full)

    # .nojekyll：告诉 Pages「别用 Jekyll 处理我」。
    # 少了它会多一道构建、还会吞掉下划线开头的文件，静态站点一律加上。
    with open(os.path.join(DST, ".nojekyll"), "w", encoding="utf-8") as f:
        f.write("")

    print("已同步 %d 个文件，%.1f MB → docs/" % (n, total / 1048576.0))
    print("下一步：git add docs && git commit && git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
