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

# 网页版引擎跑起来必需的那几份 Pyodide 文件（缺一浏览器就起不来）。
# 顺序无所谓，main 会逐个去镜像拉。.part 是下载中的临时名，拉完才 rename 成正名。
FILES = ["pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm",
         "python_stdlib.zip", "pyodide-lock.json"]

# 下载镜像，按顺序逐个试——前面的挂了就自动换下一个。{v} 会被版本号替换。
# 前两个是 jsdelivr 的不同 CDN 厂商（cdn / fastly），再不行换 unpkg，最后兜底国内 npmmirror。
MIRRORS = [
    "https://cdn.jsdelivr.net/pyodide/v{v}/full/",
    "https://fastly.jsdelivr.net/pyodide/v{v}/full/",
    "https://unpkg.com/pyodide@{v}/",
    "https://registry.npmmirror.com/pyodide/{v}/files/",
]


def human(n):
    """把字节数 n 格式化成带单位的人话字符串：B / KB / MB / GB。

    参数 n：字节数（int / float）。
    返回：如 "3.2 MB" 这样的字符串，用于在进度里显示下载大小。
    逻辑：每满 1024 就升一个单位，最后兜底用 GB，避免超大数字滚成长串。
    """
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f GB" % n


def fetch(url, dst):
    """从 url 下载一个文件，写到本地 dst（整块流式拷贝，不占内存）。

    参数：
      url  待下载地址（来自 MIRRORS 模板拼出来的完整 URL）；
      dst  本地目标路径。
    返回：下载完成后 dst 的字节大小（os.path.getsize）。
    实现：带自定义 User-Agent 发 GET 请求，timeout=60 秒防卡死；
          用 shutil.copyfileobj 边收边写，适合 wasm 这种大文件。
    删了会怎样：main 没法下载任何文件，整个脚本失去意义。
    """
    req = urllib.request.Request(url, headers={"User-Agent": "STMG-getpyodide"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)
    return os.path.getsize(dst)


def main(argv=None):
    """get_pyodide.py 的命令行入口：把 Pyodide 全套文件拉到本地目录。

    参数 argv：命令行参数列表，默认 None 时取 sys.argv。支持：
      --version  指定 Pyodide 版本（默认 0.26.2）；
      --out      指定下载目录（默认 stmg/pyodide/）；
      --force    已存在的文件也重新下载（默认跳过已存在且非空的）。
    流程：
      1. 解析参数，建好输出目录；
      2. 对 FILES 里每个文件名：已存在且非空就跳过；否则依次试 MIRRORS
         里的镜像，第一个成功的就收下，全失败记进 fail；
      3. 全部成功返回 0，有失败返回 1（方便 CI 判定）。
    被谁调用：文件末尾 `if __name__ == "__main__"` 里 sys.exit(main())。
    删了会怎样：htmlpub 发布网页时无法自带 Pyodide，只能靠浏览器联网拉，
                国内网络不稳就会退回内置解释器。
    """
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
