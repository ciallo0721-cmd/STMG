#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 Pyodide 拉到本地 —— 网页版的 WebAssembly 引擎。

    python tools/get_pyodide.py
    python tools/get_pyodide.py --version 0.26.2
    python tools/get_pyodide.py --out D:/pyodide

下完的东西放在 `stmg/pyodide/`，之后 `tools/htmlpub.py` 发布网页时会**自动带上**，
浏览器从同目录加载，不用联网、不用跨域、打开就是秒进。

为什么需要这一步：国内的 jsdelivr 时通时不通，Pyodide 主 wasm 有 9MB，
浏览器端往往等不到就超时了，然后退回内置解释器。拉一份到本地最省事。

下过的文件会跳过，可以随时重跑补缺。
"""

import argparse
import os
import shutil
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(ROOT, "stmg", "pyodide")

FILES = ["pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm",
         "python_stdlib.zip", "pyodide-lock.json"]

MIRRORS = [
    "https://cdn.jsdelivr.net/pyodide/v{v}/full/",
    "https://fastly.jsdelivr.net/pyodide/v{v}/full/",
    "https://unpkg.com/pyodide@{v}/",
    "https://registry.npmmirror.com/pyodide/{v}/files/",
]


def human(n):
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f GB" % n


def fetch(url, dst):
    req = urllib.request.Request(url, headers={"User-Agent": "STMG-getpyodide"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)
    return os.path.getsize(dst)


def main(argv=None):
    ap = argparse.ArgumentParser(description="下载 Pyodide 到本地")
    ap.add_argument("--version", default="0.26.2", help="Pyodide 版本，默认 0.26.2")
    ap.add_argument("--out", default=DEFAULT_OUT, help="放哪儿，默认 stmg/pyodide/")
    ap.add_argument("--force", action="store_true", help="已经有的文件也重下")
    args = ap.parse_args(argv)

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    print("目标目录：%s" % out)
    print("Pyodide 版本：%s\n" % args.version)

    ok, fail = [], []
    total = 0
    for name in FILES:
        dst = os.path.join(out, name)
        if os.path.isfile(dst) and not args.force and os.path.getsize(dst) > 0:
            size = os.path.getsize(dst)
            total += size
            ok.append(name)
            print("  [跳过] %-20s 已有 %s" % (name, human(size)))
            continue

        done = False
        for m in MIRRORS:
            url = m.format(v=args.version) + name
            t0 = time.time()
            try:
                size = fetch(url + "", dst + ".part")
                os.replace(dst + ".part", dst)
                total += size
                ok.append(name)
                print("  [完成] %-20s %s（%.1fs，来自 %s）"
                      % (name, human(size), time.time() - t0,
                         url.split("/")[2]))
                done = True
                break
            except Exception as e:                       # noqa: BLE001
                if os.path.isfile(dst + ".part"):
                    os.remove(dst + ".part")
                last = "%s: %s" % (type(e).__name__, e)
                continue
        if not done:
            fail.append(name)
            print("  [失败] %-20s %s" % (name, last))

    print()
    if not fail:
        print("全部就绪，共 %s。" % human(total))
        print("以后跑 tools/htmlpub.py 会自动把这份 Pyodide 打包进网页，离线也能跑引擎。")
        return 0
    print("有 %d 个文件没下下来：%s" % (len(fail), ", ".join(fail)))
    print("网络不稳的话重跑一次这个脚本——下好的不会重下，只补缺的。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
