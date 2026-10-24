#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 webmaker/ 组装成可以直接跑的制作器产物（dist/maker/）。

    python tools/build_maker.py
    python tools/build_maker.py --out dist/maker --open

产物结构：

    index.html                制作器外壳
    css/app.css
    js/editor.js              编辑器
    js/storage.js             项目存储 + zip
    js/engine.js              Pyodide 桥
    js/player.js              播放器（预览和导出共用）
    js/exporter.js            导出
    js/app.js                 主控
    js/engine-src.js          ← 构建时生成：整个 stmg 引擎的 Python 源码
    js/pyodide-manifest.js    ← 构建时生成：pyodide/ 里有哪些文件
    pyodide/                  WebAssembly 引擎（一个 .wasm + 几个 .js）

为什么要生成 engine-src.js 而不是运行时 fetch 一堆 .py：
  1. 少几十个请求，打开快；
  2. 导出的单文件 HTML 要把源码内联进去，直接读变量最省事；
  3. 制作器离线也能用（只要整个目录一起拷走）。

引擎源码清单必须和 stmg/runtime.py 的顶层 import 对齐 —— 少一个模块，
Pyodide 里 import 直接就炸，而且页面只会白屏不报错（这个坑踩过）。
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "webmaker")
OUT = os.path.join(ROOT, "dist", "maker")
ENGINE = os.path.join(ROOT, "stmg")
PYODIDE = os.path.join(ENGINE, "pyodide")

# 网页版引擎要带哪些 .py。和 tools/htmlpub.py 的 WEB_MODULES 保持一致，
# 只多一个 webtools.py（制作器的检查接口）。
WEB_MODULES = [
    "errors.py", "markdown.py", "parser.py", "runtime.py",
    "pack.py", "crypto.py", "stdlib_api.py", "stmos.py",
    "options.py", "save.py", "web_bridge.py", "avg.py",
    "webtools.py",
]

WEB_INIT = '''# -*- coding: utf-8 -*-
"""STMG 引擎（网页版子集：解析 + 运行 + 网页桥 + 制作器工具，不含界面）。"""

from .errors import STMFatal, Issue, level_name        # noqa: F401
from .parser import Script, parse_file, parse_text     # noqa: F401
from .runtime import Runtime                           # noqa: F401

__version__ = "1.0.0"
'''


def js_lit(obj):
    """转成能安全塞进 <script> 的 JS 字面量。"""
    import json
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return (s.replace("</", "<\\/")
             .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def build_engine_src(out):
    """把 stmg/*.py 打成一个 JS 变量。"""
    src = {"/stmg_root/stmg/__init__.py": WEB_INIT}
    missing = []
    for name in WEB_MODULES:
        p = os.path.join(ENGINE, name)
        if not os.path.isfile(p):
            missing.append(name)
            continue
        with open(p, "r", encoding="utf-8") as f:
            src["/stmg_root/stmg/" + name] = f.read()
    if missing:
        print("!! stmg/ 里少了：%s" % "、".join(missing))
        print("   网页版引擎会 import 失败，先确认这些文件在不在")
    text = ("/* 构建产物，不要手改。源文件在 stmg/*.py */\n"
            "window.STMG_ENGINE_SRC=" + js_lit(src) + ";\n")
    p = os.path.join(out, "js", "engine-src.js")
    write(p, text)
    return len(src), os.path.getsize(p)


def build_manifest(out):
    """列出 pyodide/ 里的文件，导出器照着打包。"""
    names = []
    if os.path.isdir(PYODIDE):
        for fn in sorted(os.listdir(PYODIDE)):
            if os.path.isfile(os.path.join(PYODIDE, fn)):
                names.append(fn)
    if not names:
        print("!! stmg/pyodide/ 是空的 —— 先跑 python tools/get_pyodide.py")
    text = ("/* 构建产物，不要手改 */\n"
            "window.STMG_PYODIDE_FILES=" + js_lit(names) + ";\n")
    write(os.path.join(out, "js", "pyodide-manifest.js"), text)
    return names


# 制作器自己也要跑在 http 上（file:// 加载不了 wasm），给它配一个零依赖启动器。
# 和导出器生成的那份是同一套逻辑，改一处记得改另一处（js/exporter.js 的 PS1）。
SERVE_PS1 = r'''# STMG 制作器本地启动器：起一个最小 http 服务，然后打开浏览器。
# 为什么不能直接双击 index.html：浏览器在 file:// 下不加载 WebAssembly。
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = 8000
while ($true) {
  try {
    $l = New-Object System.Net.HttpListener
    $l.Prefixes.Add("http://localhost:$port/")
    $l.Start()
    break
  } catch {
    $port++
    if ($port -gt 8100) { Write-Host '找不到可用端口'; Read-Host; exit 1 }
  }
}
Write-Host "STMG 制作器已启动：http://localhost:$port/"
Write-Host '关掉这个窗口就停止。'
Start-Process "http://localhost:$port/index.html"
$mime = @{ '.html'='text/html; charset=utf-8'; '.js'='application/javascript';
  '.css'='text/css'; '.wasm'='application/wasm'; '.json'='application/json';
  '.zip'='application/zip'; '.md'='text/plain; charset=utf-8';
  '.png'='image/png'; '.jpg'='image/jpeg'; '.jpeg'='image/jpeg';
  '.webp'='image/webp'; '.gif'='image/gif'; '.svg'='image/svg+xml';
  '.mp3'='audio/mpeg'; '.ogg'='audio/ogg'; '.wav'='audio/wav';
  '.m4a'='audio/mp4'; '.flac'='audio/flac' }
while ($l.IsListening) {
  $ctx = $l.GetContext()
  $rel = [Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath).TrimStart('/')
  if ([string]::IsNullOrEmpty($rel)) { $rel = 'index.html' }
  $p = Join-Path $root ($rel -replace '/', '\')
  try {
    if (Test-Path -LiteralPath $p -PathType Leaf) {
      $ext = [IO.Path]::GetExtension($p).ToLower()
      $ct = $mime[$ext]; if (-not $ct) { $ct = 'application/octet-stream' }
      $bytes = [IO.File]::ReadAllBytes($p)
      $ctx.Response.ContentType = $ct
      $ctx.Response.Headers.Add('Cache-Control', 'no-store')
      $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    } else {
      $ctx.Response.StatusCode = 404
      $b = [Text.Encoding]::UTF8.GetBytes('404 ' + $rel)
      $ctx.Response.OutputStream.Write($b, 0, $b.Length)
    }
  } catch { }
  $ctx.Response.Close()
}
'''

START_BAT = (
    "@echo off\r\n"
    "chcp 65001 >nul\r\n"
    "cd /d \"%~dp0\"\r\n"
    "echo 正在启动 STMG 制作器，浏览器马上打开...\r\n"
    "powershell -NoProfile -ExecutionPolicy Bypass -File \"%~dp0serve.ps1\"\r\n"
    "if errorlevel 1 pause\r\n"
)


def build_launcher(out):
    """给制作器自己也配一个双击启动的入口。

    .ps1 必须带 UTF-8 BOM：Windows 自带的脚本宿主读无 BOM 的文件会按系统
    ANSI 解码，中文注释变成乱码、还可能把引号配错，直接报「缺少右 }」。
    这个坑不写下来下次还会踩。
    """
    with open(os.path.join(out, "serve.ps1"), "w", encoding="utf-8-sig",
              newline="\n") as f:
        f.write(SERVE_PS1)
    write(os.path.join(out, "启动制作器.bat"), START_BAT)


def main(argv):
    out = OUT
    i = 1
    while i < len(argv):
        if argv[i] == "--out" and i + 1 < len(argv):
            out = os.path.abspath(argv[i + 1]); i += 2
        else:
            i += 1

    if not os.path.isdir(SRC):
        print("找不到 webmaker/：%s" % SRC)
        return 2

    print("清理旧产物：%s" % out)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)

    # 1. 前端源码
    for dirpath, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        rel = os.path.relpath(dirpath, SRC)
        dst_dir = out if rel == "." else os.path.join(out, rel)
        os.makedirs(dst_dir, exist_ok=True)
        for fn in files:
            if fn.startswith("."):
                continue
            shutil.copyfile(os.path.join(dirpath, fn), os.path.join(dst_dir, fn))

    # 2. Pyodide
    if os.path.isdir(PYODIDE):
        shutil.copytree(PYODIDE, os.path.join(out, "pyodide"), dirs_exist_ok=True)
    else:
        os.makedirs(os.path.join(out, "pyodide"), exist_ok=True)

    # 3. 生成物
    n_mod, src_size = build_engine_src(out)
    files = build_manifest(out)
    build_launcher(out)

    # 4. 统计
    total = 0
    for dirpath, dirs, fs in os.walk(out):
        for fn in fs:
            total += os.path.getsize(os.path.join(dirpath, fn))

    print("-" * 58)
    print("引擎模块：%d 个（engine-src.js %.1f KB）" % (n_mod, src_size / 1024.0))
    print("Pyodide ：%d 个文件 %s" % (
        len(files), "、".join(files[:3]) + ("…" if len(files) > 3 else "")))
    print("总大小　：%.1f MB" % (total / 1024.0 / 1024.0))
    print("产物　　：%s" % out)
    print("-" * 58)
    print("跑起来：")
    print("  cd \"%s\"" % out)
    print("  python -m http.server 8000")
    print("  浏览器打开 http://localhost:8000/")
    print("注意：直接双击 index.html 不行 —— file:// 下浏览器不让加载 wasm。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
