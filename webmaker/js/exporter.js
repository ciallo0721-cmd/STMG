/* ==========================================================================
   STMG 制作器 · 导出器

   exportProject  纯项目包（script.stm + 素材），丢进桌面版 STMG 仓库就能跑
   exportWeb      网页版（index.html + assets + pyodide），丢 GitHub Pages 就能分享
   exportDesktop  桌面版（网页版 + 本地启动器 + exe 打包脚本），解压双击就玩
   exportRenpy    把 .stm 交给 tools/stm2renpy.py 是不可能的（浏览器里没那个脚本），
                  这里只导出一个「交给桌面版转换」的说明 + 原剧本
   ========================================================================== */
(function () {
  "use strict";

  var _cache = {};          // 文件文本缓存
  var _pyCache = null;      // pyodide 二进制缓存（14MB，只读一次）

  function text(path) {
    if (_cache[path] != null) return Promise.resolve(_cache[path]);
    return fetch(path + "?v=" + Date.now(), { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("读不到 " + path + "（HTTP " + r.status + "）");
        return r.text();
      })
      .then(function (t) { _cache[path] = t; return t; });
  }

  function buf(path) {
    return fetch(path).then(function (r) {
      if (!r.ok) throw new Error("读不到 " + path);
      return r.arrayBuffer();
    }).then(function (b) { return new Uint8Array(b); });
  }

  function pyodideFiles() {
    var list = window.STMG_PYODIDE_FILES || [];
    if (!list.length) {
      list = ["pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm",
              "python_stdlib.zip", "pyodide-lock.json"];
    }
    return list;
  }

  async function loadPyodideBits(onProgress) {
    if (_pyCache) return _pyCache;
    var files = pyodideFiles();
    var out = [];
    for (var i = 0; i < files.length; i++) {
      onProgress && onProgress("打包引擎 " + (i + 1) + "/" + files.length + "：" + files[i]);
      try {
        out.push({ name: "pyodide/" + files[i], data: await buf("pyodide/" + files[i]) });
      } catch (e) {
        // 缺文件不致命（比如没有 lock），但要让人知道
        console.warn("[导出] 跳过缺失的 " + files[i] + "：" + e.message);
      }
    }
    if (!out.length) throw new Error("pyodide/ 目录是空的，导出的包里没有引擎");
    _pyCache = out;
    return out;
  }

  /* ---------------- 素材条目 ---------------- */
  async function assetEntries(proj, prefix, onProgress) {
    var out = [];
    var names = Object.keys(proj.files).filter(function (p) {
      return window.STMGFS.isAsset(p);
    }).sort();
    for (var i = 0; i < names.length; i++) {
      var f = proj.files[names[i]];
      if (!f || !f.blob) continue;
      onProgress && onProgress("打包素材 " + (i + 1) + "/" + names.length + "：" + names[i]);
      out.push({ name: prefix + names[i], data: new Uint8Array(await f.blob.arrayBuffer()) });
    }
    return out;
  }

  function escHtml(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function jsLit(o) {
    return JSON.stringify(o).replace(/</g, "\\u003c").replace(/\u2028/g, "\\u2028")
      .replace(/\u2029/g, "\\u2029");
  }
  function safeName(s) {
    return String(s || "项目").replace(/[\\/:*?"<>|]+/g, "_").slice(0, 48) || "项目";
  }

  /* 从 custom/gui.py 里抠几个界面参数（真正执行 Python 太重，正则够用） */
  function uiFromGuiPy(text) {
    var out = {};
    if (!text) return out;
    function num(k) {
      var m = new RegExp(k + '\\s*["\']?\\s*\\]?\\s*=\\s*([0-9.]+)').exec(text);
      return m ? parseFloat(m[1]) : null;
    }
    var ts = num("text_size");
    if (ts && ts > 6) out.fs = Math.round(ts * 1.05);
    var bh = num("box_h");
    if (bh && bh > 0 && bh <= 1) out.box = Math.round(bh * 100);
    var m = /title_bg\s*["\']?\s*\]?\s*=\s*["']([^"']+)["']/.exec(text);
    if (m) out.titleBg = m[1];
    return out;
  }

  /* ---------------- 播放器配置 ---------------- */
  function playerCfg(proj, scriptText, optionsText, extra) {
    var files = proj.files;
    var guiPy = files["custom/gui.py"] && files["custom/gui.py"].text;
    var ui = uiFromGuiPy(guiPy);

    var title = proj.name || "STMG";
    var m = /title\s*=\s*"([^"]*)"/i.exec(scriptText || "");
    if (m) title = m[1];
    var size = /Size\s*=\s*(\d+)\s*[xX×]\s*(\d+)/.exec(scriptText || "");
    var font = /Font\s*=\s*"([^"]*)"/i.exec(scriptText || "");
    var ver = /Ver\s*=\s*"([^"]*)"/i.exec(scriptText || "");

    return Object.assign({
      title: title,
      ver: "v" + ((ver && ver[1]) || "1.0.0"),
      w: size ? parseInt(size[1], 10) : 1280,
      h: size ? parseInt(size[2], 10) : 720,
      font: ('"' + ((font && font[1]) || "Microsoft YaHei") + '"'),
      box: ui.box || 26,
      fs: ui.fs || (size ? Math.max(16, Math.round(parseInt(size[2], 10) * 0.028)) : 19),
      key: "stmg:" + (proj.id || safeName(title)),
      mode: "local",
      engineLabel: "WebAssembly 引擎",
      scriptText: scriptText || "",
      optionsText: optionsText || "",
      assets: {}
    }, extra || {});
  }

  /* ---------------- 生成 index.html ---------------- */
  async function buildHtml(proj, onProgress) {
    onProgress && onProgress("读取引擎脚本…");
    var playerJs = await text("js/player.js");
    var engineJs = await text("js/engine.js");

    var files = proj.files;
    var scriptText = (files["script.stm"] && files["script.stm"].text) || "";
    var optionsText = (files["options.stm"] && files["options.stm"].text) || "";
    var cfg = playerCfg(proj, scriptText, optionsText);

    var srcJs = "window.STMG_ENGINE_SRC=" + jsLit(window.STMG_ENGINE_SRC || {}) + ";";
    var maniJs = "window.STMG_PYODIDE_FILES=" + jsLit(window.STMG_PYODIDE_FILES || []) + ";";

    return [
      "<!DOCTYPE html>",
      '<html lang="zh-CN">',
      "<head>",
      '<meta charset="utf-8">',
      '<meta name="viewport" content="width=device-width,initial-scale=1">',
      '<meta name="color-scheme" content="dark">',
      "<title>" + escHtml(cfg.title) + "</title>",
      "<style>",
      window.STMG_PLAYER.css,
      "</style>",
      "</head>",
      "<body>",
      window.STMG_PLAYER.body,
      "<script>" + srcJs + "</script>",
      "<script>" + maniJs + "</script>",
      "<script>" + engineJs + "</script>",
      "<script>" + playerJs + "</script>",
      "<script>",
      "STMG_PLAYER.boot(" + jsLit(cfg) + ");",
      "</script>",
      "</body>",
      "</html>"
    ].join("\n");
  }

  /* ---------------- 本地启动器（不依赖 Python） ---------------- */
  var PS1 = [
    "# STMG 本地启动器：起一个最小 http 服务，然后打开浏览器。",
    "# 为什么不能直接双击 index.html：浏览器在 file:// 下不加载 WebAssembly。",
    "$ErrorActionPreference = 'Stop'",
    "$root = Split-Path -Parent $MyInvocation.MyCommand.Path",
    "$port = 8765",
    "while ($true) {",
    "  try {",
    "    $l = New-Object System.Net.HttpListener",
    "    $l.Prefixes.Add(\"http://localhost:$port/\")",
    "    $l.Start()",
    "    break",
    "  } catch {",
    "    $port++",
    "    if ($port -gt 8800) { Write-Host '找不到可用端口'; Read-Host; exit 1 }",
    "  }",
    "}",
    "Write-Host \"STMG 已启动：http://localhost:$port/\"",
    "Write-Host '关掉这个窗口就停止游戏。'",
    "Start-Process \"http://localhost:$port/index.html\"",
    "$mime = @{ '.html'='text/html; charset=utf-8'; '.js'='application/javascript';",
    "  '.css'='text/css'; '.wasm'='application/wasm'; '.json'='application/json';",
    "  '.zip'='application/zip'; '.png'='image/png'; '.jpg'='image/jpeg';",
    "  '.jpeg'='image/jpeg'; '.webp'='image/webp'; '.gif'='image/gif';",
    "  '.mp3'='audio/mpeg'; '.ogg'='audio/ogg'; '.wav'='audio/wav';",
    "  '.m4a'='audio/mp4'; '.flac'='audio/flac'; '.svg'='image/svg+xml' }",
    "while ($l.IsListening) {",
    "  $ctx = $l.GetContext()",
    "  $rel = [Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath).TrimStart('/')",
    "  if ([string]::IsNullOrEmpty($rel)) { $rel = 'index.html' }",
    "  $p = Join-Path $root ($rel -replace '/', '\\')",
    "  try {",
    "    if (Test-Path -LiteralPath $p -PathType Leaf) {",
    "      $ext = [IO.Path]::GetExtension($p).ToLower()",
    "      $ct = $mime[$ext]; if (-not $ct) { $ct = 'application/octet-stream' }",
    "      $bytes = [IO.File]::ReadAllBytes($p)",
    "      $ctx.Response.ContentType = $ct",
    "      $ctx.Response.Headers.Add('Cache-Control', 'no-store')",
    "      $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)",
    "    } else {",
    "      $ctx.Response.StatusCode = 404",
    "      $b = [Text.Encoding]::UTF8.GetBytes('404 ' + $rel)",
    "      $ctx.Response.OutputStream.Write($b, 0, $b.Length)",
    "    }",
    "  } catch { }",
    "  $ctx.Response.Close()",
    "}",
    ""
  ].join("\r\n");

  var BAT = [
    "@echo off",
    "chcp 65001 >nul",
    "cd /d \"%~dp0\"",
    "echo 正在启动 STMG 游戏，浏览器马上打开...",
    "powershell -NoProfile -ExecutionPolicy Bypass -File \"%~dp0serve.ps1\"",
    "if errorlevel 1 pause",
    ""
  ].join("\r\n");

  var SERVE_PY = [
    "# -*- coding: utf-8 -*-",
    "\"\"\"STMG 本地启动器（Python 版，和 serve.ps1 二选一）。",
    "",
    "    python serve.py",
    "",
    "双击 start_game.py 也行。浏览器会自己打开。",
    "\"\"\"",
    "import http.server, os, socketserver, sys, threading, webbrowser",
    "",
    "ROOT = os.path.dirname(os.path.abspath(__file__))",
    "PORT = 8765",
    "",
    "",
    "class Handler(http.server.SimpleHTTPRequestHandler):",
    "    extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map)",
    "    extensions_map.update({'.wasm': 'application/wasm', '.js': 'application/javascript',",
    "                           '.mjs': 'application/javascript', '.json': 'application/json'})",
    "",
    "    def __init__(self, *a, **kw):",
    "        super().__init__(*a, directory=ROOT, **kw)",
    "",
    "    def log_message(self, *a):",
    "        pass",
    "",
    "",
    "def main():",
    "    port = PORT",
    "    while port < PORT + 40:",
    "        try:",
    "            httpd = socketserver.TCPServer(('127.0.0.1', port), Handler)",
    "            break",
    "        except OSError:",
    "            port += 1",
    "    else:",
    "        print('找不到可用端口'); return 1",
    "    url = 'http://localhost:%d/index.html' % port",
    "    print('STMG 已启动：' + url)",
    "    print('关掉这个窗口就停止游戏。')",
    "    threading.Timer(0.6, lambda: webbrowser.open(url)).start()",
    "    try:",
    "        httpd.serve_forever()",
    "    except KeyboardInterrupt:",
    "        pass",
    "    return 0",
    "",
    "",
    "if __name__ == '__main__':",
    "    sys.exit(main())",
    ""
  ].join("\r\n");

  var START_PY = [
    "# -*- coding: utf-8 -*-",
    "\"\"\"双击我就能玩（需要装了 Python 3）。\"\"\"",
    "import os, runpy, sys",
    "os.chdir(os.path.dirname(os.path.abspath(__file__)))",
    "runpy.run_path('serve.py', run_name='__main__')",
    ""
  ].join("\r\n");

  var BUILD_PY = [
    "# -*- coding: utf-8 -*-",
    "\"\"\"把整个游戏打成一个 exe（PyInstaller）。",
    "",
    "用法：",
    "    pip install pyinstaller",
    "    python build_exe.py",
    "",
    "生成的 exe 在 dist/ 里，双击就启动本地服务并打开浏览器。",
    "注意：exe 里打的是这个目录的全部内容（index.html / assets / pyodide），",
    "体积大约 30~40MB，这是 WebAssembly 引擎本身的重量。",
    "\"\"\"",
    "import os, subprocess, sys",
    "",
    "ROOT = os.path.dirname(os.path.abspath(__file__))",
    "",
    "",
    "def main():",
    "    try:",
    "        import PyInstaller  # noqa: F401",
    "    except ImportError:",
    "        print('没装 PyInstaller，先跑：pip install pyinstaller')",
    "        return 1",
    "    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',",
    "            '--onefile', '--name', 'STMG-Game',",
    "            '--add-data', 'index.html' + os.pathsep + '.',",
    "            '--add-data', 'serve.py' + os.pathsep + '.']",
    "    for d in ('assets', 'pyodide'):",
    "        p = os.path.join(ROOT, d)",
    "        if os.path.isdir(p):",
    "            args += ['--add-data', d + os.pathsep + d]",
    "    args.append('exe_main.py')",
    "    print(' '.join(args))",
    "    return subprocess.call(args, cwd=ROOT)",
    "",
    "",
    "if __name__ == '__main__':",
    "    sys.exit(main())",
    ""
  ].join("\r\n");

  var EXE_MAIN = [
    "# -*- coding: utf-8 -*-",
    "\"\"\"PyInstaller 的入口：找到打包进去的资源目录，起服务、开浏览器。\"\"\"",
    "import os, sys, runpy",
    "",
    "if getattr(sys, 'frozen', False):",
    "    os.chdir(sys._MEIPASS)",
    "else:",
    "    os.chdir(os.path.dirname(os.path.abspath(__file__)))",
    "",
    "runpy.run_path('serve.py', run_name='__main__')",
    ""
  ].join("\r\n");

  var BUILD_BAT = [
    "@echo off",
    "chcp 65001 >nul",
    "cd /d \"%~dp0\"",
    "echo 需要先装 Python 3 和 PyInstaller。",
    "python -c \"import PyInstaller\" 2>nul || python -m pip install pyinstaller",
    "python build_exe.py",
    "echo.",
    "echo 打完收工，去 dist\\ 里找 STMG-Game.exe",
    "pause",
    ""
  ].join("\r\n");

  var README = function (name, isDesktop) {
    return [
      "STMG 网页版 —— " + name,
      "=" .repeat(40),
      "",
      "【怎么玩】",
      isDesktop
        ? "  双击「启动游戏.bat」（推荐，不依赖 Python）\n"
          + "  或者：装了 Python 的话双击 start_game.py\n"
          + "  会起一个本地 http 服务并自动打开浏览器。"
        : "  直接把这个目录丢到任意静态网站托管上（GitHub Pages / Netlify / Nginx），\n"
          + "  打开 index.html 就是游戏。",
      "",
      "【为什么不能直接双击 index.html】",
      "  浏览器在 file:// 协议下不允许加载 WebAssembly（CORS 限制），",
      "  引擎起不来。必须通过 http:// 访问。",
      "",
      "【想打包成 exe】",
      "  双击「打包EXE.bat」。它会装 PyInstaller 并把整个目录打成一个 exe。",
      "  生成的 exe 在 dist/ 里，30~40MB（WebAssembly 引擎本身就 13MB）。",
      "  exe 的本质是「内置 http 服务 + 启动浏览器」，不是原生程序。",
      "",
      "【目录说明】",
      "  index.html     游戏本体（引擎源码、播放器都内联在里面）",
      "  assets/        你的图片和音频",
      "  pyodide/       WebAssembly 里的 CPython（一个 wasm + 几个 js）",
      "  serve.ps1      Windows 自带的 PowerShell 写的静态服务器",
      "  serve.py       Python 版服务器（可选）",
      "",
      "【改东西】",
      "  回到 STMG 制作器改剧本，重新导出即可。这里的 index.html 是生成物，",
      "  手改会在下次导出时被覆盖。",
      ""
    ].join("\r\n");
  };

  /* ---------------- 对外 ---------------- */
  async function exportProject(proj) {
    var entries = await window.STMGFS.materialize(window.STMGFS.projectEntries(proj));
    var data = window.STMGFS.makeZip(entries);
    return {
      blob: new Blob([data], { type: "application/zip" }),
      name: safeName(proj.name) + "_项目.zip"
    };
  }

  async function exportWeb(proj, onProgress, desktop) {
    onProgress && onProgress("生成 index.html…");
    var html = await buildHtml(proj, onProgress);
    var td = new TextEncoder();
    var entries = [{ name: "index.html", data: td.encode(html) }];

    entries = entries.concat(await assetEntries(proj, "assets/", onProgress));
    entries = entries.concat(await loadPyodideBits(onProgress));

    if (desktop) {
      entries.push({ name: "启动游戏.bat", data: td.encode(BAT) });
      // 开头的 BOM 不能省：Windows 自带脚本宿主读无 BOM 的 UTF-8 会按 ANSI 解码，
      // 中文注释一乱，引号就配错，脚本直接报语法错误。
      entries.push({ name: "serve.ps1", data: td.encode("\ufeff" + PS1) });
      entries.push({ name: "serve.py", data: td.encode(SERVE_PY) });
      entries.push({ name: "start_game.py", data: td.encode(START_PY) });
      entries.push({ name: "打包EXE.bat", data: td.encode(BUILD_BAT) });
      entries.push({ name: "build_exe.py", data: td.encode(BUILD_PY) });
      entries.push({ name: "exe_main.py", data: td.encode(EXE_MAIN) });
    }
    entries.push({ name: "README.txt", data: td.encode(README(proj.name || "未命名", !!desktop)) });

    onProgress && onProgress("压缩 " + entries.length + " 个文件…");
    var data = window.STMGFS.makeZip(entries);
    return {
      blob: new Blob([data], { type: "application/zip" }),
      name: safeName(proj.name) + (desktop ? "_桌面版.zip" : "_网页版.zip"),
      size: data.length,
      count: entries.length
    };
  }

  /* 单文件 HTML：素材内联成 data URI，适合「一个文件就能发给人」 */
  async function exportSingleHtml(proj, onProgress) {
    onProgress && onProgress("读取素材…");
    var cfg = playerCfg(proj, "", "");
    var assets = {};
    var names = Object.keys(proj.files).filter(function (p) { return window.STMGFS.isAsset(p); });
    for (var i = 0; i < names.length; i++) {
      var f = proj.files[names[i]];
      if (!f || !f.blob) continue;
      onProgress && onProgress("内联素材 " + (i + 1) + "/" + names.length);
      assets[names[i]] = await new Promise(function (res) {
        var fr = new FileReader();
        fr.onload = function () { res(fr.result); };
        fr.readAsDataURL(f.blob);
      });
    }
    var scriptText = (proj.files["script.stm"] && proj.files["script.stm"].text) || "";
    var optionsText = (proj.files["options.stm"] && proj.files["options.stm"].text) || "";
    cfg = playerCfg(proj, scriptText, optionsText, { assets: assets });

    var playerJs = await text("js/player.js");
    var engineJs = await text("js/engine.js");
    var html = [
      "<!DOCTYPE html>", '<html lang="zh-CN"><head><meta charset="utf-8">',
      '<meta name="viewport" content="width=device-width,initial-scale=1">',
      "<title>" + escHtml(cfg.title) + "</title>",
      "<style>" + window.STMG_PLAYER.css + "</style></head><body>",
      window.STMG_PLAYER.body,
      "<script>window.STMG_ENGINE_SRC=" + jsLit(window.STMG_ENGINE_SRC || {}) + ";</script>",
      "<script>window.STMG_PYODIDE_FILES=" + jsLit(window.STMG_PYODIDE_FILES || []) + ";</script>",
      "<script>" + engineJs + "</script>",
      "<script>" + playerJs + "</script>",
      "<script>STMG_PLAYER.boot(" + jsLit(cfg) + ");</script>",
      "</body></html>"
    ].join("\n");
    return {
      blob: new Blob([html], { type: "text/html;charset=utf-8" }),
      name: safeName(proj.name) + ".html"
    };
  }

  window.STMG_EXPORT = {
    project: exportProject,
    web: function (p, cb) { return exportWeb(p, cb, false); },
    desktop: function (p, cb) { return exportWeb(p, cb, true); },
    singleHtml: exportSingleHtml,
    buildHtml: buildHtml,
    safeName: safeName
  };
})();
