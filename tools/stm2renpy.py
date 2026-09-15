#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""STMG → Ren'Py 转换器（renpy2stm 的反向）。

    python tools/stm2renpy.py demo
    python tools/stm2renpy.py projects/我的游戏 --out dist/我的游戏_renpy
    python tools/stm2renpy.py projects/我的游戏 --no-assets     只转剧本，不拷素材
    python tools/stm2renpy.py projects/我的游戏 --title 游戏名

产物（默认 dist/<项目名>_renpy/）：

    game/
    ├── script.rpy        剧本正文，label start: 开始
    ├── stmg_config.rpy   标题 / 分辨率 / 角色定义 / 图像定义 / 兼容变量
    ├── images/           从 bg/ png/ gui/ 拷过来的图
    └── audio/            从 music/ 拷过来的音频
    转换报告.md            转换统计 + 需要手工处理的地方

把 `game/` 里的东西拷进 Ren'Py 工程（或者直接把整个 game/ 当工程皮肤），
再用 Ren'Py SDK 打开就能跑。

能转的：
    S.character("角色1")             ->  define 角色1 = Character("角色1")
    S.character("png/立绘.png", ...)  ->  image 立绘的 tag 定义 + show
    S.cg("bg/room.png")              ->  scene bg_room
    S.picture("png/note.png")        ->  show pic_note
    S.play / sound / voice / stop    ->  play music / sound / voice，stop music
    S.hide("x") / S.hide("sprite")   ->  hide x / 逐个 hide 在场立绘
    S.jump("x") / S.end()            ->  jump x / jump stmg_ending
    SET 变量 = 值                     ->  $ 变量 = 值
    Choose: + If "选项":             ->  menu + if "选项" in stmg_chosen
    Question:                        ->  $ stmg_answer = renpy.input(...)
    STM.display("文字")              ->  $ renpy.notify("文字")
    **粗体** [color=] [size=]        ->  {b} / {color=} / {size=}
    "前缀" + STM.ANSWER + "后缀"      ->  "前缀[stmg_answer]后缀"

转不了的（会进「转换报告.md」，不静默丢）：
    stm.os(...) 受控文件操作、R.api 联网（Ren'Py 里得自己用 renpy.fetch 写）、
    STM.python 扩展库、嵌套在分支里的 label
"""

import os
import re
import shutil
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from stmg import parser                                  # noqa: E402
from stmg.markdown import TOKEN_RE, strip_quotes         # noqa: E402

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".avif")
AUDIO_EXT = (".ogg", ".mp3", ".wav", ".opus", ".m4a", ".flac")

# 项目里这些顶层目录名是「同类素材」，搬进 Ren'Py 工程时要把这一层吃掉，
# 否则会写出 audio/audio/xxx 这种看着像 bug 的路径。
AUDIO_TOP = ("audio", "music", "sound", "se", "voice", "bgm", "sfx")
IMAGE_TOP = ("images", "image", "img", "bg", "png", "pic", "picture",
             "cg", "sprite", "gui", "texture")


def relocate(rel, kind):
    """素材在 Ren'Py 工程里落到哪：图片统一进 images/，音频统一进 audio/。"""
    parts = [x for x in rel.replace("\\", "/").split("/") if x not in ("", ".")]
    top = IMAGE_TOP if kind == "image" else AUDIO_TOP
    if len(parts) > 1 and parts[0].lower() in top:
        parts = parts[1:]
    return "/".join((["images"] if kind == "image" else ["audio"]) + parts)


def kind_of(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    return ""


def walk_assets(proj_dir):
    """项目里所有素材：(相对路径, 绝对路径)。"""
    out = []
    for dirpath, dirs, files in os.walk(proj_dir):
        dirs[:] = [d for d in dirs if not d.startswith((".", "_"))
                   and d not in (".venv", "dist", "game", "custom")]
        for fn in files:
            if kind_of(fn):
                full = os.path.join(dirpath, fn)
                out.append((os.path.relpath(full, proj_dir).replace("\\", "/"), full))
    out.sort()
    return out

# STM 的运行时命名空间 → Ren'Py 的 store 变量
STORE_MAP = {
    "STM.ANSWER": "stmg_answer",
    "STM.API": "stmg_api",
    "STM.OS": "stmg_os",
    "STM.NAME": "stmg_name",
    "STM.Q": "stmg_q",
    "R.RESULT": "stmg_api",
}

RESERVED = {
    "if", "else", "elif", "for", "while", "return", "def", "class", "import",
    "from", "as", "in", "is", "not", "and", "or", "pass", "none", "true",
    "false", "try", "except", "finally", "with", "lambda", "global",
    "nonlocal", "del", "assert", "raise", "yield", "break", "continue",
    "call", "jump", "menu", "show", "scene", "hide", "label", "play",
    "stop", "voice", "window", "nvl", "init", "python", "screen", "pause",
    "transform", "style", "image", "define", "default", "text", "at", "use",
    "on", "key", "bar", "grid", "side", "vbox", "hbox", "frame",
}

POS_OK = ("left", "center", "right", "truecenter", "topleft", "topright",
          "bottomleft", "bottomright", "offscreenleft", "offscreenright")


# --------------------------------------------------------------------------- #
# 文本工具
# --------------------------------------------------------------------------- #
def sanitize(name, fallback="x"):
    """把任意名字变成 Ren'Py 认的标识符（保留中文，其余换成下划线）。"""
    s = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", name or "").strip("_")
    if not s:
        s = fallback
    if s[0].isdigit() or s[0] == "_":
        s = "%s_%s" % (fallback, s)
    if s.lower() in RESERVED:
        s += "_v"
    return s


def esc_text(s):
    """Ren'Py 文本里的 [ { % 都是保留字符，纯文本部分得转义。"""
    s = s.replace("[", "[[").replace("{", "{{").replace("%", "%%")
    return s


def lit(s):
    """变成 Ren'Py 认得的一行字符串字面量。"""
    out = (s.replace("\\", "\\\\").replace('"', '\\"')
            .replace("\r", "").replace("\n", "\\n"))
    return '"%s"' % out


def md2rpy(text):
    """STMG 的 md 内联标记 → Ren'Py 的 text tag。"""
    out, pos = [], 0
    for m in TOKEN_RE.finditer(text):
        if m.start() > pos:
            out.append(esc_text(text[pos:m.start()]))
        pos = m.end()
        if m.group("colortext") is not None:
            out.append("{color=%s}%s{/color}"
                       % (m.group("color"), esc_text(m.group("colortext"))))
        elif m.group("sizetext") is not None:
            out.append("{size=%s}%s{/size}"
                       % (m.group("size"), esc_text(m.group("sizetext"))))
        elif m.group("rbase") is not None:
            out.append("%s{size=-6}(%s){/size}"
                       % (esc_text(m.group("rbase")), esc_text(m.group("rtext"))))
        elif m.group("bold") is not None:
            out.append("{b}%s{/b}" % esc_text(m.group("bold")))
        elif m.group("strike") is not None:
            out.append("{s}%s{/s}" % esc_text(m.group("strike")))
        elif m.group("code") is not None:
            # Ren'Py 没有等宽 tag，去掉反引号保留内容
            out.append(esc_text(m.group("code")))
        elif m.group("italic") is not None:
            out.append("{i}%s{/i}" % esc_text(m.group("italic")))
    if pos < len(text):
        out.append(esc_text(text[pos:]))
    return "".join(out)


def split_concat(raw):
    """把 `"甲" + STM.ANSWER + "乙"` 拆成 ['"甲"', 'STM.ANSWER', '"乙"']。"""
    parts, buf, in_str, esc, i = [], [], False, False, 0
    while i < len(raw):
        c = raw[i]
        if in_str:
            buf.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
                buf.append(c)
            elif c == "+":
                parts.append("".join(buf).strip())
                buf = []
            else:
                buf.append(c)
        i += 1
    parts.append("".join(buf).strip())
    return [p for p in parts if p]


def is_str_literal(s):
    s = s.strip()
    return len(s) >= 2 and s[0] == '"' and s[-1] == '"' and '"' not in s[1:-1]


def map_store(expr):
    """STM.ANSWER / R.RESULT 之类的运行时名字 → Ren'Py 变量。"""
    out = expr
    for k, v in STORE_MAP.items():
        out = re.sub(r"\b%s\b" % re.escape(k), v, out)
    out = re.sub(r"\bSTM\.OS\b", "stmg_os", out)
    # and / or / not → Ren'Py 的 Python 表达式也认，但 trivially 保持原样
    return out


# --------------------------------------------------------------------------- #
# 转换主体
# --------------------------------------------------------------------------- #
class Conv(object):
    def __init__(self, script, name, proj_dir=None):
        self.script = script
        self.name = name
        self.proj_dir = proj_dir
        self.assets = {}         # 剧本里的相对路径 -> Ren'Py 工程里的路径
        self._taken = set()      # 已经占掉的目标路径（防止两个源文件撞车）
        self.chars = {}          # 显示名 -> 变量名
        self.char_order = []
        self.images = {}         # image 名字（含空格分隔的 tag/variant）-> 定义行
        self.spr_by_path = {}    # (tag, path) -> image 名
        self.bg_by_path = {}     # 背景路径 -> image 名（同一张图只定义一次）
        self.pic_by_path = {}    # 贴图路径 -> image 名
        self.variant_used = {}   # tag -> set(已用 variant)
        self.tags_live = []      # 当前在场的立绘 tag（保持顺序）
        self.pic_name = None     # 当前叠加的 picture 名
        self.bg_name = None
        self.labels = set()
        self.todo = []
        self.stats = Counter()
        self.tmp = 0
        self.last_q = None
        self.menu_n = 0
        self.warned_pos = set()

    # ---------------- 资源 ---------------- #
    def _register(self, rel):
        """给一个素材相对路径分配 Ren'Py 工程里的落点（同一个源永远同一个落点）。"""
        key = rel.replace("\\", "/").strip().lstrip("/")
        if key in self.assets:
            return self.assets[key]
        dst = relocate(key, kind_of(key) or "image")
        base, ext = os.path.splitext(dst)
        i = 2
        while dst.lower() in self._taken:
            dst = "%s_%d%s" % (base, i, ext)
            i += 1
        self._taken.add(dst.lower())
        self.assets[key] = dst
        return dst

    def scan_assets(self):
        """先把项目里所有素材登记一遍，这样拷贝和引用不会各算各的。"""
        if not self.proj_dir:
            return
        for rel, _full in walk_assets(self.proj_dir):
            self._register(rel)

    def asset_ref(self, path):
        """STMG 里的相对路径 → Ren'Py 工程里的引用路径。"""
        p = (path or "").replace("\\", "/").strip().lstrip("/")
        if not p:
            return ""
        if not kind_of(p):
            return p                              # 不是图片/音频，原样放着
        return self.assets.get(p) or self._register(p)

    def _uniq(self, pool, name):
        if name not in pool:
            return name
        i = 2
        while "%s_%d" % (name, i) in pool:
            i += 1
        return "%s_%d" % (name, i)

    def sprite_name(self, tag, path):
        """立绘 image 名 = 「tag variant」，同 tag 会互相替换（和 STMG 一致）。

        tag 和文件名撞了（比如 tag=aming_normal、文件也叫 aming_normal.png）就只留一个词，
        省得写出 `show aming_normal aming_normal` 这种。
        """
        key = (tag, path)
        if key in self.spr_by_path:
            return self.spr_by_path[key]
        tag_s = sanitize(tag, "sprite")
        stem = os.path.splitext(os.path.basename(path.replace("\\", "/")))[0]
        variant = sanitize(stem, "v")
        used = self.variant_used.setdefault(tag_s, set())
        if variant != tag_s:
            variant = self._uniq(used, variant)
            used.add(variant)
        full = tag_s if variant == tag_s else "%s %s" % (tag_s, variant)
        self.images[full] = 'image %s = %s' % (
            full, lit(self.asset_ref(path)))
        self.spr_by_path[key] = full
        return full

    def bg_image(self, path):
        if path in self.bg_by_path:
            return self.bg_by_path[path]
        stem = os.path.splitext(os.path.basename(path.replace("\\", "/")))[0]
        base = sanitize(stem, "bg")
        nm = base if base.lower().startswith("bg") else "bg_" + base
        nm = self._uniq(self.images, nm)
        self.images[nm] = 'image %s = %s' % (nm, lit(self.asset_ref(path)))
        self.bg_by_path[path] = nm
        return nm

    def pic_image(self, path):
        if path in self.pic_by_path:
            return self.pic_by_path[path]
        stem = os.path.splitext(os.path.basename(path.replace("\\", "/")))[0]
        base = sanitize(stem, "pic")
        nm = base if base.lower().startswith("pic") else "pic_" + base
        nm = self._uniq(self.images, nm)
        self.images[nm] = 'image %s = %s' % (nm, lit(self.asset_ref(path)))
        self.pic_by_path[path] = nm
        return nm

    def char_var(self, disp):
        if disp in self.chars:
            return self.chars[disp]
        var = sanitize(disp, "char")
        i = 2
        while var in (self.chars.values()):
            var = "%s_%d" % (sanitize(disp, "char"), i)
            i += 1
        self.chars[disp] = var
        self.char_order.append(disp)
        return var

    # ---------------- 文本 ---------------- #
    def say_text(self, raw, line, depth):
        """台词原文 → (要预先插入的 $ 行, Ren'Py 字符串字面量)。

        md 标记可能跨越拼接（`"[color=x]**" + STM.ANSWER + "**[/color]"`），
        所以先把变量换成哨兵，整条拼好再统一做 md 转换，最后才把哨兵换成插值。
        """
        raw = (raw or "").strip()
        pre = []
        if "+" not in raw and "STM." not in raw:
            text = raw[1:-1] if is_str_literal(raw) else strip_quotes(raw)
            return pre, lit(md2rpy(text))

        reps, parts = [], []                        # [(哨兵, Ren'Py 插值)]
        for c in split_concat(raw):
            if is_str_literal(c):
                parts.append(c[1:-1])
                continue
            expr = map_store(c)
            if re.match(r"^[A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*$", expr):
                val = "[%s]" % expr                 # 简单变量直接插值
            else:
                self.tmp += 1
                name = "stmg_tmp%d" % self.tmp
                pre.append("%s$ %s = %s" % ("    " * depth, name, expr))
                val = "[%s]" % name
            ph = "\x01%d\x01" % len(reps)
            reps.append((ph, val))
            parts.append(ph)

        rpy = md2rpy("".join(parts))
        for ph, val in reps:
            rpy = rpy.replace(ph, val)
        return pre, lit(rpy)

    # ---------------- 语句 ---------------- #
    def emit(self, stmts, depth, lines):
        pad = "    " * depth
        for s in stmts:
            k = s["k"]
            fn = getattr(self, "do_" + k, None)
            if fn is None:
                self.todo.append((s.get("line"), "不认识的语句类型 %s" % k, ""))
                lines.append("%s# [没转] 不认识的语句 %s" % (pad, k))
                continue
            fn(s, depth, lines)

    # --- 台词 ---
    def do_say(self, s, depth, lines):
        pad = "    " * depth
        if not s.get("who"):
            pre, text = self.say_text(s["text"], s["line"], depth)
            lines.extend(pre)
            lines.append("%s%s" % (pad, text))
            self.stats["旁白"] += 1
            return
        who = self.char_var(s["who"])
        pre, text = self.say_text(s["text"], s["line"], depth)
        lines.extend(pre)
        lines.append("%s%s %s" % (pad, who, text))
        self.stats["台词"] += 1

    # --- python 代码块 ---
    def do_pycode(self, s, depth, lines):
        pad = "    " * depth
        self.todo.append((s.get("line"),
                          "python 代码块转不过去（Ren'Py 里没有对应写法）",
                          "搬到 Ren'Py 就手工改成 python: 块或 $ 语句"))
        lines.append("%s# [没转] python 代码块（%d 行）"
                     % (pad, len(s.get("code") or [])))

    # --- 角色注册 ---
    def do_define(self, s, depth, lines):
        if s.get("name"):
            self.char_var(s["name"])
            self.stats["角色声明"] += 1

    # --- 立绘 ---
    def do_sprite(self, s, depth, lines):
        pad = "    " * depth
        path = s.get("path") or ""
        kw = s.get("kwargs") or {}
        args = s.get("args") or []
        tag = kw.get("tag") or os.path.splitext(
            os.path.basename(path.replace("\\", "/")))[0]
        pos = str(kw.get("pos") or (args[1] if len(args) > 1 else "center")).lower()
        full = self.sprite_name(tag, path)
        tag_s = full.split(" ")[0]
        out = "%sshow %s" % (pad, full)
        if pos in POS_OK:
            out += " at %s" % pos
        elif pos and pos not in self.warned_pos:
            self.warned_pos.add(pos)
            self.todo.append((s.get("line"), "站位 %s Ren'Py 没有对应 transform，"
                                             "已按 center 处理" % pos, path))
            out += " at center"
        lines.append(out)
        if tag_s not in self.tags_live:
            self.tags_live.append(tag_s)
        self.stats["立绘"] += 1

    # --- 背景 / 叠加图 ---
    def do_bg(self, s, depth, lines):                       # 不会直接出现
        pass

    def do_picture(self, s, depth, lines):
        pad = "    " * depth
        if s.get("path"):
            self.pic_name = self.pic_image(s["path"])
            lines.append("%sshow %s" % (pad, self.pic_name))
        elif self.pic_name:
            lines.append("%shide %s" % (pad, self.pic_name))
            self.pic_name = None
        self.stats["贴图"] += 1

    # --- 变量 ---
    def do_set(self, s, depth, lines):
        pad = "    " * depth
        name = s["name"]
        expr = s["expr"]
        if name.upper() == "STM.Q":
            self.last_q = expr
            self.stats["输入提示"] += 1
            return
        if name.upper().startswith("STM."):
            lines.append("%s# [没转] %s = %s（STM 命名空间只读，Ren'Py 里没有对应）"
                         % (pad, name, expr))
            self.todo.append((s.get("line"), "STM 内部变量赋值无法转换", name))
            return
        lines.append("%s$ %s = %s" % (pad, sanitize(name, "var"), map_store(expr)))
        self.stats["赋值"] += 1

    # --- 输入 ---
    def do_question(self, s, depth, lines):
        pad = "    " * depth
        prompt = s.get("prompt") or self.last_q or ""
        if is_str_literal(prompt):
            text = lit(md2rpy(prompt[1:-1]))
        elif "+" in prompt or "STM." in prompt:
            pre, text = self.say_text(prompt, s.get("line"), depth)
            lines.extend(pre)
        else:
            text = lit(prompt or "请输入")
        lines.append("%s$ stmg_answer = renpy.input(%s, length=40)"
                     % (pad, text))
        self.stats["玩家输入"] += 1

    # --- 条件 ---
    def do_if(self, s, depth, lines):
        pad = "    " * depth
        cond = (s.get("cond") or "").strip()
        if is_str_literal(cond):
            expr = '"%s" in stmg_chosen' % cond[1:-1]
        else:
            expr = map_store(cond) or "True"
        lines.append("%sif %s:" % (pad, expr))
        self.emit(s.get("body") or [], depth + 1, lines)
        eb = s.get("else_body") or []
        if eb:
            lines.append("%selse:" % pad)
            self.emit(eb, depth + 1, lines)
        self.stats["条件分支"] += 1

    def do_else(self, s, depth, lines):
        self.todo.append((s.get("line"), "落单的 Else（前面没有 If），已跳过", "Else:"))

    # --- 选择支 ---
    def do_choose(self, s, depth, lines):
        pad = "    " * depth
        self.menu_n += 1
        opts = s.get("options") or []
        lines.append("%smenu:" % pad)
        for o in opts:
            lines.append('%s    %s:' % (pad, lit(md2rpy(o))))
            lines.append('%s        $ stmg_chosen.add(%s)' % (pad, lit(o)))
        if not opts:
            lines.append("%s    \"（空选择支）\":" % pad)
            lines.append("%s        pass" % pad)
        self.stats["选择支"] += 1

    # --- 标签 ---
    def do_label(self, s, depth, lines):
        name = s.get("name") or ""
        if depth > 1:
            self.todo.append((s.get("line"), "嵌套在分支里的 label Ren'Py 不支持，已跳过",
                              name))
            return
        if name.lower() == "start":
            return                       # start 由调用方统一处理
        lines.append("label %s:" % sanitize(name, "label"))

    # --- stm.os ---
    def do_stm_os(self, s, depth, lines):
        pad = "    " * depth
        lines.append("%s# [没转] stm.os %s(%s)", )
        lines[-1] = "%s# [没转] stm.os %s(%s)" % (pad, s.get("op"), s.get("path"))
        self.todo.append((s.get("line"),
                          "stm.os 受控文件操作 Ren'Py 没有对应功能",
                          "stm.os(%s(\"%s\"))" % (s.get("op"), s.get("path"))))
        self.stats["stm.os（未转）"] += 1

    # --- 函数调用 ---
    def do_call(self, s, depth, lines):
        obj = (s.get("obj") or "").upper()
        m = s["method"].lower()
        pad = "    " * depth
        args = s.get("args") or []
        kw = s.get("kwargs") or {}
        a0 = args[0] if args else ""

        if obj == "S":
            if m in ("cg", "bg", "background"):
                self.tags_live = []
                if a0:
                    self.bg_name = self.bg_image(a0)
                    lines.append("%sscene %s" % (pad, self.bg_name))
                else:
                    self.bg_name = None
                    lines.append("%sscene black" % pad)
                self.stats["换背景"] += 1
            elif m == "picture":
                self.do_picture({"path": a0}, depth, lines)
            elif m == "play":
                loop = str(kw.get("loop", "true")).lower() not in ("false", "0", "no")
                lines.append("%splay music %s%s"
                             % (pad, lit(self.asset_ref(a0)), "" if loop else " noloop"))
                self.stats["BGM"] += 1
            elif m == "sound":
                lines.append("%splay sound %s" % (pad, lit(self.asset_ref(a0))))
                self.stats["音效"] += 1
            elif m == "voice":
                lines.append("%svoice %s" % (pad, lit(self.asset_ref(a0))))
                self.stats["语音"] += 1
            elif m == "stop":
                what = (a0 or "bgm").lower()
                if what in ("bgm", "music", "all"):
                    lines.append("%sstop music" % pad)
                if what in ("sound", "se", "all"):
                    lines.append("%sstop sound" % pad)
                if what in ("voice", "all"):
                    lines.append("%sstop voice" % pad)
                self.stats["停音频"] += 1
            elif m == "hide":
                what = (a0 or "sprite").lower()
                if what in ("picture", "pic"):
                    if self.pic_name:
                        lines.append("%shide %s" % (pad, self.pic_name))
                        self.pic_name = None
                elif what == "sprite":
                    for t in self.tags_live:
                        lines.append("%shide %s" % (pad, t))
                    self.tags_live = []
                elif what == "all":
                    for t in self.tags_live:
                        lines.append("%shide %s" % (pad, t))
                    self.tags_live = []
                    if self.pic_name:
                        lines.append("%shide %s" % (pad, self.pic_name))
                        self.pic_name = None
                else:
                    tag_s = sanitize(what, "sprite")
                    lines.append("%shide %s" % (pad, tag_s))
                    if tag_s in self.tags_live:
                        self.tags_live.remove(tag_s)
                self.stats["隐藏图层"] += 1
            elif m == "jump":
                if a0 in self.labels:
                    lines.append("%sjump %s" % (pad, sanitize(a0, "label")))
                else:
                    lines.append("%s# [没转] S.jump(\"%s\") 找不到这个标签" % (pad, a0))
                    self.todo.append((s.get("line"), "跳转的标签不存在",
                                      "S.jump(\"%s\")" % a0))
                self.stats["跳转"] += 1
            elif m == "end":
                lines.append("%sjump stmg_ending" % pad)
                self.stats["结束"] += 1
            elif m == "character":
                self.todo.append((s.get("line"), "S.character 参数看不懂，已跳过",
                                  str(s)))
            else:
                lines.append("%s# [没转] S.%s(...)" % (pad, s["method"]))
                self.todo.append((s.get("line"), "没实现的内建函数",
                                  "S.%s(...)" % s["method"]))

        elif obj == "STM":
            if m == "display":
                lines.append("%s$ renpy.notify(%s)" % (pad, lit(strip_quotes(a0))))
                self.stats["提示"] += 1
            else:
                lines.append("%s# [没转] STM.%s(...)" % (pad, s["method"]))
                self.todo.append((s.get("line"), "STM.%s 没有对应实现" % s["method"],
                                  str(s)))

        elif obj == "R":
            lines.append("%s# [没转] R.api(url=%s) —— Ren'Py 里请用 renpy.fetch() 自己写"
                         % (pad, kw.get("url") or a0))
            self.todo.append((s.get("line"), "R.api 联网请求无法自动转换；"
                                             "Ren'Py 可用 renpy.fetch(url) 替代",
                              "R.api(url=\"%s\")" % (kw.get("url") or a0)))
            self.stats["R.api（未转）"] += 1

        else:
            lines.append("%s# [没转] %s.%s(...)" % (pad, obj, s["method"]))
            self.todo.append((s.get("line"), "不认识的调用", str(s)))

    # ---------------- 顶层 ---------------- #
    def run(self):
        body = list(self.script.body)
        # 收集所有 label，方便判断 jump 目标
        for s in self.script.walk():
            if s["k"] == "label" and s.get("name"):
                self.labels.add(s["name"])
        self.labels.add("Start")

        lines = ["## 本文件由 tools/stm2renpy.py 从 %s 自动生成"
                 % os.path.basename(self.script.path), ""]

        has_start = bool(body) and body[0]["k"] == "label" \
            and (body[0].get("name") or "").lower() == "start"
        if has_start:
            body = body[1:]
        lines.append("label start:")
        self.emit(body, 1, lines)
        lines.append("")
        lines.append("    jump stmg_ending" if self.script.ending else "    return")

        if self.script.ending:
            lines.append("")
            lines.append("label stmg_ending:")
            self.emit(self.script.ending, 1, lines)
            lines.append("    return")
        return lines

    def config_lines(self):
        h = self.script.header
        out = ["## 本文件由 tools/stm2renpy.py 自动生成",
               "## 标题 / 分辨率 / 角色 / 图像定义 / STMG 运行时兼容变量",
               "",
               'define config.name = _("%s")' % (h.get("title") or self.name),
               'define config.version = "%s"' % (h.get("ver") or "1.0.0"),
               "",
               "## 基准分辨率（你的 Ren'Py 工程已经配好了就删掉这两行）",
               "init python:",
               "    gui.init(%d, %d)" % (self.script.width, self.script.height),
               "",
               "## 字体：STMG 写的是字体名，Ren'Py 要的是字体文件。",
               "## 想保持一致就把字体文件放进 game/fonts/，再取消下面两行的注释。",
               '## define gui.text_font = "fonts/你的字体.ttf"',
               '## define gui.name_text_font = "fonts/你的字体.ttf"',
               "",
               "## STMG 运行时变量（剧本里 STM.ANSWER / STM.OS / STM.API 的落点）",
               'default stmg_answer = ""',
               'default stmg_os = ""',
               "default stmg_api = None",
               'default stmg_name = ""',
               'default stmg_q = ""',
               "## 记录玩家选过哪些选项——STMG 的 If \"选项名\" 就是查这个",
               "default stmg_chosen = set()",
               ""]

        if self.char_order:
            out.append("## 角色（来自 S.character(\"名字\")）")
            for disp in self.char_order:
                out.append('define %s = Character("%s")'
                           % (self.chars[disp], disp.replace('"', '\\"')))
            out.append("")

        if self.images:
            out.append("## 图像定义（来自 S.cg / S.character(立绘) / S.picture）")
            out.extend(sorted(self.images.values()))
            out.append("")
        return out


# --------------------------------------------------------------------------- #
# 素材 / 报告
# --------------------------------------------------------------------------- #
def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f TB" % n


def copy_assets(proj_dir, game_dir, conv):
    """按 conv 登记好的落点拷素材，引用路径和磁盘路径保证一致。"""
    n, total = 0, 0
    for rel, dst_rel in sorted(conv.assets.items()):
        src = os.path.join(proj_dir, rel.replace("/", os.sep))
        if not os.path.isfile(src):
            continue                    # 剧本引用了但磁盘上没有这个文件
        dst = os.path.join(game_dir, dst_rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        n += 1
        total += os.path.getsize(dst)
    return n, total


def main(argv):
    args = argv[1:]
    if not args:
        print(__doc__)
        return 2

    src = os.path.abspath(args[0])
    out = None
    title = None
    do_assets = True

    i = 1
    while i < len(args):
        a = args[i]
        if a == "--out":
            i += 1
            out = args[i]
        elif a == "--title":
            i += 1
            title = args[i]
        elif a == "--no-assets":
            do_assets = False
        i += 1

    script_path = src if os.path.isfile(src) else os.path.join(src, "script.stm")
    if not os.path.isfile(script_path):
        print("找不到剧本：%s" % script_path)
        return 2
    proj_dir = os.path.dirname(os.path.abspath(script_path))
    name = os.path.basename(proj_dir)

    script = parser.parse_file(script_path)
    if script.error_count():
        print("剧本有 %d 个错误，先修好再转（用 tools/check.py 看详情）："
              % script.error_count())
        for it in script.issues[:10]:
            print("   %s" % it)
        return 2

    if title:
        script.header["title"] = title

    out = os.path.abspath(out or os.path.join(ROOT, "dist", "%s_renpy" % name))
    game = os.path.join(out, "game")
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(game)

    conv = Conv(script, name, proj_dir)
    conv.scan_assets()
    body_lines = conv.run()
    cfg_lines = conv.config_lines()

    with open(os.path.join(game, "stmg_config.rpy"), "w", encoding="utf-8") as f:
        f.write("\n".join(cfg_lines) + "\n")
    with open(os.path.join(game, "script.rpy"), "w", encoding="utf-8") as f:
        f.write("\n".join(body_lines) + "\n")

    if do_assets:
        n, total = copy_assets(proj_dir, game, conv)
        print("素材　　：复制 %d 个文件，%s" % (n, human(total)))
    else:
        print("素材　　：已跳过（--no-assets）")

    # 报告
    with open(os.path.join(out, "转换报告.md"), "w", encoding="utf-8") as f:
        f.write("# STMG → Ren'Py 转换报告\n\n")
        f.write("来源：`%s`\n\n输出：`%s`\n\n" % (script_path, out))
        f.write("## 转换统计\n\n| 项目 | 数量 |\n|---|---|\n")
        for k, v in conv.stats.most_common():
            f.write("| %s | %d |\n" % (k, v))
        f.write("| 角色 | %d |\n| 图像定义 | %d |\n\n"
                % (len(conv.chars), len(conv.images)))
        f.write("## 怎么用\n\n")
        f.write("1. 装好 Ren'Py SDK，新建一个空工程\n"
                "2. 把这里 `game/` 下的 `script.rpy` / `stmg_config.rpy` / "
                "`images/` / `audio/` 拷进工程的 `game/`\n"
                "3. 用 Ren'Py SDK 启动一次即可\n\n")
        f.write("## 需要手工处理的\n\n")
        if not conv.todo:
            f.write("没有。全部转换成功。\n")
        else:
            f.write("| 行 | 原因 | 原文 |\n|---|---|---|\n")
            for ln, why, text in conv.todo:
                f.write("| %s | %s | `%s` |\n"
                        % (ln or "-", why, str(text).replace("|", "\\|")))
        f.write("\n## 已知差异\n\n")
        f.write("- STMG 的 `If \"选项名\"` 在 Ren'Py 里靠 `stmg_chosen` 集合实现，"
                "语义一致\n"
                "- STMG 没有转场，Ren'Py 有；想加 `with dissolve` 得自己写\n"
                "- `stm.os` 受控文件操作、`R.api` 联网、`STM.python` 扩展库"
                "没有对应实现，已标成注释\n"
                "- 等宽标记 `` `x` `` 去掉了反引号（Ren'Py 没有等宽 text tag）\n"
                "- 打字机、快进、存读档这些用的是 Ren'Py 自带界面，"
                "STMG 的 gui/ 皮肤不会带过来\n")

    print("-" * 56)
    print("剧本　　：%s" % os.path.join(game, "script.rpy"))
    print("配置　　：%s" % os.path.join(game, "stmg_config.rpy"))
    if conv.todo:
        print("要手工处理 %d 处，清单见 转换报告.md" % len(conv.todo))
    else:
        print("全部转换成功，没有遗留。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
