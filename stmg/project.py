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
              os.path.join("gui", "button")]

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
| `script.stm` | 主剧本 |
| `options.stm` | 标题、加密口令、打包规则 |

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
    return path


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
