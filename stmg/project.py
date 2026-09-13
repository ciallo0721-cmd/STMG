# -*- coding: utf-8 -*-
"""STMG 项目：发现 / 新建 / 元数据 / 最近打开。

「项目」就是一个目录，里面有 script.stm + options.stm 加一堆素材文件夹。
启动器只认这个结构，不关心剧本内容。
"""

import json
import os
import re
import shutil
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_DIR = os.path.join(ROOT, "projects")
DEMO_DIR = os.path.join(ROOT, "demo")
CFG_PATH = os.path.join(ROOT, ".stmg_launcher.json")

ASSET_DIRS = ["bg", "png", "music", os.path.join("gui", "textbox"),
              os.path.join("gui", "button"), "custom"]

# 新建项目时会从 stmg/templates/ 拷过来的自定义文件
CUSTOM_FILES = [("custom_gui.py", "gui.py"),
                ("custom_markdown.py", "markdown.py")]

# 内嵌引擎时跳过的目录 / 后缀（pyodide 约 13MB，发布 HTML 时另行拷贝）
EMBED_SKIP_DIRS = {"__pycache__", "pyodide"}
EMBED_SKIP_EXT = {".pyc"}

TEMPLATE_SCRIPT = """<
Size={size}
title="{title}"
Ver="1.0.0"
Pack="com.example.{slug}"
Lang="cn"
Font="Microsoft YaHei"
>
<
Start:
<-- 角色先注册，再让他说话 -->
S.character("主角")

<-- 素材还没放也没关系，引擎会自动画占位块 -->
S.cg("bg/room.png")

"这是「{title}」的第一句话。改我，改我！"

主角"你好，世界。"

<-- 变量第一次出现必须用 SET -->
SET 好感度 = 0

Choose:
    "认真回答":"随便敷衍"

If "认真回答":
    SET 好感度 = 好感度 + 10
    主角"（认真脸）这是认真的回答。"
If "随便敷衍":
    SET 好感度 = 好感度 - 5
    主角"啊……这样啊。"

STM.Q = "请给自己取个名字："
Question:

"你好，**" + STM.ANSWER + "**。"

If 好感度 >= 10:
    主角"嗯，你看起来挺靠谱的。"
Else:
    主角"……算了，就这样吧。"

<-- 想加背景音乐就把文件放进 music/，然后取消下面这行的注释 -->
<-- S.play("music/bgm.mp3") -->

S.cg("")
主角"那么，剧本到此结束。改 script.stm 继续写吧。"
>
<
"感谢游玩"
>
"""

TEMPLATE_OPTIONS = """<
About = "{title} —— 用 STMG 引擎做的游戏。"
Enc = "{key}"
dec = "*.stm,*.png,*.jpg,*.mp3,*.wav,*.ogg"
AllowNet = "true"
>
"""

TEMPLATE_README = """# {title}

用 [STMG](https://github.com/ciallo0721-cmd) 做的视觉小说。

## 怎么改

1. 用启动器点「编辑剧本」，或者直接改 `script.stm`
2. 改完先点「语法检查」，再去「启动游戏」
3. 满意了点「打包发布」，产物在 `dist/{name}/`

## 文件夹

| 目录 | 放什么 |
|---|---|
| `bg/` | 背景图 |
| `png/` | 立绘、贴图 |
| `music/` | BGM / 音效 / 语音 |
| `gui/` | 文本框图片、按钮图片（没有就用默认样式） |
| `custom/` | 界面配置和自定义标记（见下） |
| `script.stm` | 主剧本 |
| `options.stm` | 标题、加密口令、打包规则 |

## 改界面

`custom/gui.py` 里写 `CONFIG = {{...}}` 就能改界面：对话框位置大小、
名字框颜色、立绘站位、标题背景图、标题曲……文件里每项都有注释和默认值，
去掉 `#` 改数字即可。

`custom/markdown.py` 用来加自己的内联标记（比如 `[w]` 当停顿）。

两个文件删掉都能跑，引擎会退回默认外观。

## 项目自带引擎（完全开放）

这个项目目录里带着**完整的引擎源码**（`stmg/` 文件夹 + `start.py`）。

- 跑游戏：双击 `start.bat`，或 `python start.py script.stm`
- `python start.py --check script.stm` 只查语法，`--auto` 无头跑一遍

想自定义引擎行为（渲染、界面、音频、语法……），**直接改本项目里的
`stmg/*.py` 就行**——优先用的是项目自己这份，不影响启动器和其他项目。
删掉 `stmg/` 和 `start.py` 也能跑，会自动退回启动器目录里的引擎。

语法看引擎目录下的 `README.md`。
"""


# --------------------------------------------------------------------------- #
def ensure_dirs():
    if not os.path.isdir(PROJECTS_DIR):
        os.makedirs(PROJECTS_DIR, exist_ok=True)


def slugify(name):
    s = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", name).strip("_")
    return s or "game"


def is_project(path):
    return bool(path) and os.path.isfile(os.path.join(path, "script.stm"))


def script_of(path):
    return os.path.join(path, "script.stm")


def roots():
    """扫描哪些目录里放着项目。"""
    ensure_dirs()
    return [PROJECTS_DIR, DEMO_DIR]


def list_projects(extra_paths=None):
    """返回 [{path, name, title, mtime, size}]，按修改时间倒序。"""
    found = {}
    for root in roots():
        if not os.path.isdir(root):
            continue
        # demo/ 这种「目录本身就是项目」的情况
        if is_project(root):
            found[os.path.normcase(os.path.abspath(root))] = root
        for name in sorted(os.listdir(root)):
            if name.startswith("_") or name.startswith("."):
                continue
            p = os.path.join(root, name)
            if os.path.isdir(p) and is_project(p):
                found[os.path.normcase(os.path.abspath(p))] = p
    for p in (extra_paths or []):
        if is_project(p):
            found[os.path.normcase(os.path.abspath(p))] = p

    out = []
    for p in found.values():
        out.append(info(p))
    out.sort(key=lambda d: d["mtime"], reverse=True)
    return out


def info(path):
    sp = script_of(path)
    title = os.path.basename(path)
    try:
        with open(sp, "r", encoding="utf-8-sig") as f:
            head = f.read(600)
        m = re.search(r'^\s*title\s*=\s*"([^"]*)"', head, re.M)
        if m and m.group(1):
            title = m.group(1)
    except OSError:
        pass

    says = 0
    try:
        with open(sp, "r", encoding="utf-8-sig") as f:
            text = f.read()
        says = len(re.findall(r'^\s*"[^"]*"\s*$', text, re.M))
    except OSError:
        pass

    total = 0
    for dirpath, _dirs, files in os.walk(path):
        if ".stmg_save" in dirpath:
            continue
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, fn))
            except OSError:
                pass

    return {
        "path": path,
        "name": os.path.basename(path),
        "title": title,
        "mtime": os.path.getmtime(sp) if os.path.isfile(sp) else 0,
        "mtime_text": time.strftime("%Y-%m-%d %H:%M",
                                    time.localtime(os.path.getmtime(sp))
                                    if os.path.isfile(sp) else 0),
        "says": says,
        "size_text": _human(total),
    }


def _human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f TB" % n


def create_project(name, title=None, size="1280x720"):
    """新建一个空项目，返回项目路径。名字重了会自动加后缀。"""
    ensure_dirs()
    name = slugify(name)
    path = os.path.join(PROJECTS_DIR, name)
    i = 2
    while os.path.exists(path):
        path = os.path.join(PROJECTS_DIR, "%s_%d" % (name, i))
        i += 1
    path = os.path.abspath(path)

    os.makedirs(path)
    for d in ASSET_DIRS:
        os.makedirs(os.path.join(path, d), exist_ok=True)

    title = title or os.path.basename(path)
    with open(script_of(path), "w", encoding="utf-8") as f:
        f.write(TEMPLATE_SCRIPT.format(title=title, size=size,
                                       slug=slugify(os.path.basename(path)).lower()))
    with open(os.path.join(path, "options.stm"), "w", encoding="utf-8") as f:
        f.write(TEMPLATE_OPTIONS.format(title=title, key="change-me-%d" % int(time.time())))
    with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as f:
        f.write(TEMPLATE_README.format(title=title, name=os.path.basename(path)))
    copy_custom_files(path)
    embed_engine(path)
    return path


def embed_engine(path):
    """把引擎本体（stmg/ 包 + start.py + start.bat）拷进项目，项目即完全自包含。

    之后项目用自己的引擎跑：改项目里的 stmg/render.py、stmg/gui.py、
    stmg/markdown.py 等只影响这个项目，不用碰启动器目录的源码。
    已存在的文件不覆盖（size 相同的跳过），可以重复调用做增量更新。
    返回拷贝 / 更新的文件列表（相对项目目录）。
    """
    pkg_src = os.path.dirname(os.path.abspath(__file__))          # stmg/
    root = os.path.dirname(pkg_src)                                # STMG 根目录
    pkg_dst = os.path.join(path, "stmg")
    done = []

    for dirpath, dirnames, filenames in os.walk(pkg_src):
        rel = os.path.relpath(dirpath, pkg_src)
        dirnames[:] = [d for d in dirnames if d not in EMBED_SKIP_DIRS]
        dst_dir = pkg_dst if rel == "." else os.path.join(pkg_dst, rel)
        os.makedirs(dst_dir, exist_ok=True)
        for fn in sorted(filenames):
            if os.path.splitext(fn)[1].lower() in EMBED_SKIP_EXT:
                continue
            s, d = os.path.join(dirpath, fn), os.path.join(dst_dir, fn)
            try:
                if os.path.exists(d) and os.path.getsize(s) == os.path.getsize(d):
                    continue
                shutil.copyfile(s, d)
                done.append(os.path.relpath(d, path).replace("\\", "/"))
            except OSError:
                pass

    src = os.path.join(root, "start.py")
    if os.path.isfile(src) and not os.path.exists(os.path.join(path, "start.py")):
        shutil.copyfile(src, os.path.join(path, "start.py"))
        done.append("start.py")
    # 项目专用 start.bat：只跑剧本，不试图开启动器
    dst_bat = os.path.join(path, "start.bat")
    if not os.path.exists(dst_bat):
        with open(dst_bat, "w", encoding="ascii", newline="\r\n") as f:
            f.write('@echo off\r\ncd /d "%~dp0"\r\n'
                    'if exist ".venv\\Scripts\\python.exe" (\r\n'
                    '    ".venv\\Scripts\\python.exe" start.py %*\r\n'
                    ') else (\r\n'
                    '    python start.py %*\r\n'
                    ')\r\n'
                    'if errorlevel 1 pause\r\n')
        done.append("start.bat")
    return done


def copy_custom_files(path):
    """把 custom/gui.py（界面配置）和 custom/markdown.py（自定义标记）放进去。

    这两个文件是给用户随便改的：改界面尺寸、换标题图、换标题曲、加自己的
    内联标记。删掉也不影响，引擎会退回默认外观。
    """
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    dst_dir = os.path.join(path, "custom")
    os.makedirs(dst_dir, exist_ok=True)
    done = []
    for src_name, dst_name in CUSTOM_FILES:
        src = os.path.join(tpl, src_name)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(dst_dir, dst_name)
        if not os.path.exists(dst):
            shutil.copyfile(src, dst)
            done.append(dst_name)
    return done


def rename_project(path, new_name):
    new_path = os.path.join(os.path.dirname(path), slugify(new_name))
    if os.path.normcase(new_path) == os.path.normcase(path):
        return path
    if os.path.exists(new_path):
        raise OSError("已经有同名项目了：%s" % os.path.basename(new_path))
    os.rename(path, new_path)
    return new_path


def trash_project(path):
    """不真删，挪到 projects/_trash/ 下面。想找回来随时能找。"""
    ensure_dirs()
    trash = os.path.join(PROJECTS_DIR, "_trash")
    os.makedirs(trash, exist_ok=True)
    dst = os.path.join(trash, "%s_%s" % (os.path.basename(path),
                                         time.strftime("%Y%m%d_%H%M%S")))
    shutil.move(path, dst)
    return dst


# --------------------------------------------------------------------------- #
def load_cfg():
    if os.path.isfile(CFG_PATH):
        try:
            with open(CFG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            pass
    return {"recent": [], "python": "", "window": "900x620"}


def save_cfg(cfg):
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def push_recent(path):
    cfg = load_cfg()
    recent = [p for p in cfg.get("recent", [])
              if os.path.normcase(p) != os.path.normcase(path)]
    recent.insert(0, os.path.abspath(path))
    cfg["recent"] = recent[:12]
    cfg["recent"] = [p for p in cfg["recent"] if os.path.isdir(p)]
    save_cfg(cfg)
    return cfg["recent"]


# --------------------------------------------------------------------------- #
# 多语言剧本发现：script.stm 为默认版，script.<lang>.stm 为其它语言版本
# --------------------------------------------------------------------------- #
def find_languages(script_path):
    """扫描剧本所在目录，返回 {语言标记: 剧本绝对路径}。

    默认版（script.stm）的语言标记是空串 ""；script.en.stm → "en"，
    script.zh-tw.stm → "zh-tw"。没有任何语言文件时返回 {"": 默认路径}，
    这样标题界面的「语言」按钮只会在真有多版本时出现。
    """
    d = os.path.dirname(os.path.abspath(script_path))
    base = os.path.basename(script_path)
    stem, ext = os.path.splitext(base)
    out = {}
    default = os.path.join(d, base)
    if os.path.isfile(default):
        out[""] = default
    try:
        names = os.listdir(d)
    except OSError:
        return out
    pat = re.compile(re.escape(stem) + r"\.([A-Za-z][A-Za-z0-9_-]*)\.stm$", re.I)
    for f in names:
        m = pat.match(f)
        if m and f != base:
            out[m.group(1).lower()] = os.path.join(d, f)
    return out
