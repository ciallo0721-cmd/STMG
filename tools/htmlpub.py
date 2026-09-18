#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""STMG → 网页版（HTML）发布器。

    python tools/htmlpub.py demo
    python tools/htmlpub.py projects/我的游戏 --out dist/我的游戏_web
    python tools/htmlpub.py demo --engine js        用页面内置解释器（完全离线）
    python tools/htmlpub.py demo --inline           素材内联进 HTML（单文件）
    python tools/htmlpub.py demo --no-assets        不带素材，只出播放器
    python tools/htmlpub.py demo --mod example_sakura   带上指定的美化包（mod/）
    python tools/htmlpub.py demo --no-mod           不带任何美化包
    python tools/htmlpub.py demo --pyodide cdn      强制从 CDN 拉 Pyodide
    python tools/htmlpub.py demo --pyodide https://你的镜像/pyodide/v0.26.2/full/

产物（默认 dist/<项目名>_web/）：

    index.html      播放器 + 剧本，双击就能玩，也能直接丢到 GitHub Pages
    assets/         图片和音频（--inline 时不生成）
    pyodide/        WebAssembly 引擎本体（跑过一次 tools/get_pyodide.py 才会有）

引擎说明：
    默认用 **Pyodide**（WebAssembly 里的 CPython）在浏览器里跑真正的 stmg
    Python 引擎——剧本解析、变量求值、分支推进和桌面版完全同一套代码，
    所以网页上不会出现「和桌面版表现不一样」。

    先跑一次 `python tools/get_pyodide.py` 把 Pyodide 拉到本地（约 13MB），
    发布时会自动打包进产物，浏览器从同目录加载：**不联网、不跨域、秒进**。
    本地没有那份文件时才退回 CDN；CDN 拉不到会自动退回页面自带的轻量解释器。
"""

import base64
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from stmg import parser, uiconf                          # noqa: E402
from stmg import mod as modmod                            # noqa: E402

TPL_PATH = os.path.join(ROOT, "stmg", "webplayer.html")
ENGINE_DIR = os.path.join(ROOT, "stmg")

# 网页版只带「解析 + 运行 + 桥」这几块，界面由 HTML 自己画，不需要 pygame。
# 注意 save.py 不能漏：runtime.py 顶层就是 `from . import pack, save as savemod, ...`，
# 少一个文件整个包在浏览器里 import 不起来（发布时看着一切正常，打开一片空白）。
WEB_MODULES = ["errors.py", "markdown.py", "parser.py", "runtime.py",
               "pack.py", "crypto.py", "stdlib_api.py", "stmos.py",
               "options.py", "save.py", "web_bridge.py"]

WEB_INIT = '''# -*- coding: utf-8 -*-
"""STMG 引擎（网页版子集：解析 + 运行 + 网页桥，不含界面）。"""

from .errors import STMFatal, Issue, level_name        # noqa: F401
from .parser import Script, parse_file, parse_text     # noqa: F401
from .runtime import Runtime                           # noqa: F401

__version__ = "1.0.0"
'''

DEFAULT_PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.2/full/"
# 跑过 tools/get_pyodide.py 之后，这里会有一份本地的 Pyodide
LOCAL_PYODIDE = os.path.join(ENGINE_DIR, "pyodide")

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".avif")
AUDIO_EXT = (".ogg", ".mp3", ".wav", ".opus", ".m4a", ".flac", ".aac")

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".bmp": "image/bmp", ".gif": "image/gif",
        ".avif": "image/avif", ".ogg": "audio/ogg", ".mp3": "audio/mpeg",
        ".wav": "audio/wav", ".opus": "audio/opus", ".m4a": "audio/mp4",
        ".flac": "audio/flac", ".aac": "audio/aac"}


# --------------------------------------------------------------------------- #
def js_lit(obj):
    """转成能直接塞进 <script> 的 JS 字面量。

    JSON 里的 `</` 会被浏览器当成标签结束，`\u2028/\u2029` 在旧 JS 里是换行，都得转。
    """
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return (s.replace("</", "<\\/")
             .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f TB" % n


def safe_font(name):
    """字体名进 CSS，别让它带出引号或分号。"""
    s = "".join(c for c in str(name or "") if c.isalnum() or c in " -_")
    return s.strip() or "Microsoft YaHei"


def html_esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def collect_assets(proj_dir):
    out = []
    for dirpath, dirs, files in os.walk(proj_dir):
        dirs[:] = [d for d in dirs if not d.startswith((".", "_"))
                   and d not in ("custom", "dist", "game", "assets",
                                 "mod", "mod_assets")]
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in IMAGE_EXT or ext in AUDIO_EXT:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, proj_dir).replace("\\", "/")
                out.append((rel, full))
    out.sort()
    return out


def engine_sources():
    """网页版要带的 Python 源码：{虚拟路径: 源码}。

    缺文件不抛异常，但一定要吼一声：引擎是整包 import 的，少一个模块
    在浏览器里就直接 `ImportError`，玩家看到的是一片空白而不是报错。
    """
    src = {"/stmg_root/stmg/__init__.py": WEB_INIT}
    missing = []
    for name in WEB_MODULES:
        p = os.path.join(ENGINE_DIR, name)
        if not os.path.isfile(p):
            missing.append(name)
            continue
        with open(p, "r", encoding="utf-8") as f:
            src["/stmg_root/stmg/" + name] = f.read()
    if missing:
        print("引擎警告：stmg/ 里少了 %s —— 网页版引擎会 import 失败，"
              "先确认这些文件在不在" % "、".join(missing))
    return src


def api_timeout_ms():
    """网页版 R.api 的超时（毫秒）。

    常量真正的家是 stmg/web_bridge.py（桌面版那边也读它）。这里从源码里
    抠出来用，免得两边各写一份、改了一处忘了另一处。
    不 import 它是因为 web_bridge 一被导入就会给 stdlib_api / stmos 打桩，
    发布器不需要那个副作用。
    """
    try:
        with open(os.path.join(ENGINE_DIR, "web_bridge.py"), "r",
                  encoding="utf-8") as f:
            m = re.search(r"^API_TIMEOUT_MS\s*=\s*(\d+)", f.read(), re.M)
        if m:
            return int(m.group(1))
    except OSError:
        pass
    return 10000


def _walk_nodes(node, visit):
    """把剧本 AST 里每个语句节点都过一遍（不管嵌套多深）。"""
    if isinstance(node, dict):
        if "k" in node:
            visit(node)
        for v in node.values():
            _walk_nodes(v, visit)
    elif isinstance(node, list):
        for v in node:
            _walk_nodes(v, visit)


def scan_features(script):
    """扫一遍剧本，数出「网页版和桌面版表现不一样」的能力用了几次。

    只用来在发布结束时给作者提个醒：这两种写法在网页版是**降级**的
    （联网要过 CORS、文件操作只在沙箱里），提前知道比发布完再发现强。
    """
    hits = {"api": 0, "os": 0}

    def visit(nd):
        k = nd.get("k")
        if k == "stm_os":
            hits["os"] += 1
        elif (k == "call" and str(nd.get("obj") or "").upper() == "R"
              and str(nd.get("method") or "").lower() == "api"):
            hits["api"] += 1

    _walk_nodes(getattr(script, "body", None), visit)
    _walk_nodes(getattr(script, "ending", None), visit)
    return hits


def custom_css(ui, inline_assets):
    """把 custom/gui.py 里能对应上的设置翻成 CSS。"""
    rules = []
    size = ui.get("text_size")
    if isinstance(size, (int, float)) and size > 6:
        rules.append("#text{font-size:%dpx}" % int(size * 1.05))
    bg = ui.get("title_bg")
    if bg:
        key = str(bg).replace("\\", "/")
        url = inline_assets.get(key, "assets/" + key)
        rules.append("#title .bg{background:url('%s') center/cover no-repeat}" % url)
    return "\n".join(rules)


def theme_assets(css, theme, out, inline, inline_assets, do_assets=True):
    """处理美化包 theme.css 里的 url(...)：把图拷进产物目录并把路径改对。

    内联模式（--inline）则直接转成 data URI。远程地址在 modcheck 阶段就被
    拦掉了，这里再挡一次：美化包不许引用外部资源。
    """
    if not css or not theme.get("path"):
        return css
    mod_id = theme.get("id") or "mod"
    rel_prefix = "mod_assets/%s/" % mod_id

    def rep(m):
        raw = m.group(1).strip().strip("'\"")
        if not raw or raw.startswith(("data:", "#")) or "://" in raw or raw.startswith("//"):
            return m.group(0)
        rel = raw.replace("\\", "/").lstrip("/")
        if rel.startswith("../"):
            return m.group(0)
        src = os.path.join(theme["path"], rel.replace("/", os.sep))
        if not os.path.isfile(src):
            print("  美化包素材没找到，保持原样：%s" % raw)
            return m.group(0)
        ext = os.path.splitext(rel)[1].lower()
        if inline:
            with open(src, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            url = "data:%s;base64,%s" % (MIME.get(ext, "application/octet-stream"), b64)
        elif do_assets:
            dst = os.path.join(out, rel_prefix, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            url = rel_prefix + rel
        else:
            return m.group(0)
        inline_assets[rel] = url
        return "url('%s')" % url

    return re.sub(r"url\(\s*([^)]*)\)", rep, css, flags=re.I)


# --------------------------------------------------------------------------- #
def main(argv):
    args = argv[1:]
    if not args:
        print(__doc__)
        return 2

    src = os.path.abspath(args[0])
    out = None
    engine = "wasm"
    inline = False
    do_assets = True
    pyodide = "auto"                 # auto = 本地有就用本地，没有才去 CDN
    title = None
    mod_id = None
    no_mod = False

    i = 1
    while i < len(args):
        a = args[i]
        if a == "--out":
            i += 1
            out = args[i]
        elif a == "--engine":
            i += 1
            engine = args[i].lower()
        elif a == "--pyodide":
            i += 1
            pyodide = args[i]
        elif a == "--title":
            i += 1
            title = args[i]
        elif a == "--mod":
            i += 1
            mod_id = args[i]
        elif a == "--no-mod":
            no_mod = True
        elif a == "--inline":
            inline = True
        elif a == "--no-assets":
            do_assets = False
        i += 1

    if engine not in ("wasm", "js"):
        print("--engine 只能是 wasm 或 js")
        return 2

    script_path = src if os.path.isfile(src) else os.path.join(src, "script.stm")
    if not os.path.isfile(script_path):
        print("找不到剧本：%s" % script_path)
        return 2
    proj_dir = os.path.dirname(os.path.abspath(script_path))
    name = os.path.basename(proj_dir)

    with open(script_path, "r", encoding="utf-8-sig") as f:
        script_text = f.read()
    script = parser.parse_text(script_text, script_path)
    if script.error_count():
        print("剧本有 %d 个错误，先修好再发布（tools/check.py 看详情）："
              % script.error_count())
        for it in script.issues[:10]:
            print("   %s" % it)
        return 2
    if title:
        script.header["title"] = title

    opt_path = os.path.join(proj_dir, "options.stm")
    options_text = ""
    if os.path.isfile(opt_path):
        with open(opt_path, "r", encoding="utf-8-sig") as f:
            options_text = f.read()

    out = os.path.abspath(out or os.path.join(ROOT, "dist", "%s_web" % name))
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)

    # ---- Pyodide 从哪儿来 ----
    pyodide_local = False
    if pyodide == "auto":
        have_local = os.path.isfile(os.path.join(LOCAL_PYODIDE, "pyodide.js"))
        if engine == "wasm" and have_local:
            shutil.copytree(LOCAL_PYODIDE, os.path.join(out, "pyodide"),
                            dirs_exist_ok=True)
            pyodide_url = "pyodide/"
            pyodide_local = True
        else:
            pyodide_url = DEFAULT_PYODIDE
    elif pyodide == "cdn":
        pyodide_url = DEFAULT_PYODIDE
    else:
        pyodide_url = pyodide if pyodide.endswith("/") else pyodide + "/"

    # ---- 素材 ----
    assets_map = {}
    asset_n, asset_size = 0, 0
    if do_assets:
        for rel, full in collect_assets(proj_dir):
            asset_size += os.path.getsize(full)
            if inline:
                ext = os.path.splitext(rel)[1].lower()
                with open(full, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                assets_map[rel] = "data:%s;base64,%s" % (MIME.get(ext, "application/octet-stream"), b64)
            else:
                dst = os.path.join(out, "assets", rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(full, dst)
            asset_n += 1

    # ---- 项目自己的界面设置（custom/gui.py）----
    ui = uiconf.load(proj_dir, mod_id, no_mod)
    box_h = ui.get("box_h") or 0.30
    try:
        box_pct = max(12, min(60, int(float(box_h) * 100)))
    except (TypeError, ValueError):
        box_pct = 24

    # ---- 美化包（mod/）：样式 + 受限脚本 ----
    theme = modmod.load_theme(proj_dir, mod_id, disabled=no_mod)
    theme_css_text = ""
    theme_js_text = ""
    theme_label = ""
    if theme["id"] != modmod.DEFAULT_ID:
        if not theme["ok"]:
            print("美化包：%s" % theme["reason"])
        else:
            theme_label = str(theme["meta"].get("name") or theme["id"])
            theme_css_text = theme_assets(theme.get("css") or "", theme, out,
                                          inline, assets_map, do_assets)
            theme_js_text = theme.get("js") or ""
            print("美化包：%s（%s）" % (theme_label, theme["id"]))

    # ---- 渲染 ----
    with open(TPL_PATH, "r", encoding="utf-8") as f:
        tpl = f.read()

    ast = {"title": script.title, "ver": script.header.get("ver", "1.0.0"),
           "w": script.width, "h": script.height,
           "body": script.body, "ending": script.ending}
    fsize = max(16, int(script.height * 0.032))
    if isinstance(ui.get("text_size"), (int, float)):
        fsize = max(14, int(ui["text_size"] * 1.05))

    repl = {
        "__STMG_TITLE__": html_esc(script.title),
        "__STMG_VER__": html_esc("v" + str(script.header.get("ver", "1.0.0"))),
        "__STMG_ENGINE_LABEL__": "WebAssembly 引擎" if engine == "wasm" else "内置解释器",
        "__STMG_FONT__": safe_font(script.font),
        "__STMG_W__": str(script.width),
        "__STMG_H__": str(script.height),
        "__STMG_FSIZE__": str(fsize),
        "__STMG_BOX_H__": str(box_pct),
        "__STMG_CUSTOM_CSS__": custom_css(ui, assets_map),
        "__STMG_THEME_CSS__": theme_css_text,
        "__STMG_THEME_JS__": theme_js_text,
        "__STMG_THEME_NAME__": html_esc(theme_label),
        "__STMG_DATA__": js_lit(ast),
        "__STMG_ASSETS__": js_lit(assets_map),
        "__STMG_KEY__": js_lit("stmg:%s" % name),
        "__STMG_ENGINE__": js_lit(engine),
        "__STMG_PYODIDE__": js_lit(pyodide_url),
        "__STMG_PY__": js_lit(engine_sources() if engine == "wasm" else {}),
        "__STMG_SCRIPT__": js_lit(script_text),
        "__STMG_OPTIONS__": js_lit(options_text),
        # 联网超时：JS 里要的是数字字面量，页面上那句提示要的是秒，各给一份
        "__STMG_API_TIMEOUT__": str(api_timeout_ms()),
        "__STMG_API_SEC__": ("%g" % (api_timeout_ms() / 1000.0)),
    }
    for k, v in repl.items():
        tpl = tpl.replace(k, v)

    html_path = os.path.join(out, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(tpl)

    total = os.path.getsize(html_path)
    print("引擎　　：%s%s" % ("WebAssembly（Pyodide）" if engine == "wasm" else "内置解释器",
                            "，素材已内联" if (inline and do_assets) else ""))
    if engine == "wasm":
        if pyodide_local:
            print("Pyodide ：已把本地那份打包进去（离线可用、同源、打开就进）")
        else:
            print("Pyodide ：从 %s 加载" % pyodide_url)
            print("          想离线不折腾网络，先跑一次 tools/get_pyodide.py")
    if do_assets:
        print("素材　　：%d 个文件，%s" % (asset_n, human(asset_size)))
    else:
        print("素材　　：已跳过（--no-assets）")

    # ---- 网页版的能力差异提醒（剧本里真用到了才说） ----
    feat = scan_features(script)
    if feat["api"]:
        print("联网提醒：剧本里有 %d 处 R.api。网页版的密钥在源码里必然可见，"
              "跨域还要对方接口允许 CORS；%g 秒拿不到结果就当失败，剧情照常推进。"
              % (feat["api"], api_timeout_ms() / 1000.0))
    if feat["os"]:
        print("文件提醒：剧本里有 %d 处 stm.os。网页版只会写进浏览器沙箱，"
              "碰不到玩家真实磁盘；清空站点数据就找不回来了。"
              % feat["os"])

    print("-" * 56)
    print("网页　　：%s" % html_path)
    print("大小　　：%s" % human(total + (0 if inline else asset_size)))
    print("双击 index.html 就能玩；整个目录丢到 GitHub Pages 也是一个能分享的链接。")
    if inline and asset_size > 12 * 1024 * 1024:
        print("体积提醒：素材内联后 HTML 会很大（base64 会让文件涨三分之一），"
              "大项目建议去掉 --inline。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
