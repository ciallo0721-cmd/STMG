#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ren'Py → STMG 转换器。

⚠️ 状态：未完成，还没在真实工程上验证通过，先别指望它能直接转出能跑的工程。
   目前已知问题：角色声明和部分定义语句的处理还不完整。

    python tools/renpy2stm.py D:\\renpy\\ydlx\\game
    python tools/renpy2stm.py <游戏目录> --out projects/ydlx --title 印度旅行
    python tools/renpy2stm.py <游戏目录> --no-assets        只转剧本，不拷素材

能转的：
    define x = Character("名字")      ->  S.character("名字")
    image bg a = "x.jpg"             ->  解析成真实路径
    label start:                     ->  Start:
    "旁白"                            ->  "旁白"
    char "台词"                       ->  显示名"台词"
    menu: / "选项": / 缩进块            ->  Choose: + If "选项":
    if / elif / else                 ->  If / Else（elif 会展开成 Else 里套 If）
    $ var = 值                       ->  SET var = 值
    scene bg x [with fade]           ->  S.cg("...")
    show char pose [at left|right]   ->  S.character("...", pos="left", tag="char")
    hide char                        ->  S.hide("char")
    play music/sound "f"             ->  S.play / S.sound
    voice "f"                        ->  S.voice
    stop music                       ->  S.stop("bgm")
    jump 标签 / return                ->  S.jump("标签") / S.end()
    {b}{i}{color=}{size=} + [变量]     ->  **粗体** / *斜体* / [color=] / 字符串拼接
    # 注释                            ->  <-- 注释 -->

转不了的（会列进「转换报告.md」，不静默丢掉）：
    screen / transform / style / init python / python 块 / call / 自定义 transition
    大部分 with 转场（STMG 目前没有转场特效）
"""

import os
import re
import shutil
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 这些是 Ren'Py 引擎自带的界面文件，不是剧本
ENGINE_RPY = {"gui.rpy", "screens.rpy", "options.rpy", "common.rpy",
              "00console.rpy", "00default.rpy", "00library.rpy",
              "00preferences.rpy", "00accessibility.rpy", "00action_file.rpy"}

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".avif")
AUDIO_EXT = (".ogg", ".mp3", ".wav", ".opus", ".flac", ".m4a")

RE_DEF_CHAR = re.compile(r'^define\s+([\w\u4e00-\u9fff]+)\s*=\s*Character\s*\((.*)\)\s*$')
RE_DEF_NAME = re.compile(r'^define\s+config\.name\s*=\s*_?\(\s*"(.*?)"\s*\)')
RE_IMAGE = re.compile(r'^image\s+([\w\u4e00-\u9fff][\w\u4e00-\u9fff\s\-]*?)\s*=\s*"(.*?)"\s*$')
RE_LABEL = re.compile(r'^label\s+([\w.]+)\s*(?:\(.*?\))?\s*:\s*$')
RE_IF = re.compile(r'^if\s+(.+?)\s*:\s*$')
RE_ELIF = re.compile(r'^elif\s+(.+?)\s*:\s*$')
RE_ELSE = re.compile(r'^else\s*:\s*$')
RE_MENU = re.compile(r'^menu\s*(?:\(.*?\))?\s*:\s*$')
RE_OPTION = re.compile(r'^"(?P<cap>.*?)"\s*(?:if\s+(?P<cond>.+?))?\s*:\s*$')
RE_SET = re.compile(r'^\$\s*(.+)$')
RE_ASSIGN = re.compile(r'^([\w\u4e00-\u9fff][\w\u4e00-\u9fff.]*)\s*(=|\+=|-=|\*=|/=)\s*(.+)$')
RE_SAY_NAMED = re.compile(r'^(?P<who>[\w\u4e00-\u9fff]+)\s+(?P<text>".*")$')
RE_SAY_BARE = re.compile(r'^(?P<text>".*")$')
RE_SAY_VERB = re.compile(r'^(?:centered|extend|nvl\s+clear\s+)?(?P<text>".*")$')
RE_GUI_INIT = re.compile(r'gui\.init\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)')
RE_STR = re.compile(r'"(?:[^"\\]|\\.)*"')

MODIFIER = re.compile(r'\s+(?:with|at|behind|onlayer|as|zorder|nointeract)\s+')
AT_RE = re.compile(r'\bat\s+([A-Za-z_][\w,\s]*?)(?=\s+(?:with|behind|onlayer|as|zorder)\b|$)')

POS_MAP = {"left": "left", "right": "right", "center": "center",
           "truecenter": "center", "topleft": "left", "topright": "right"}

SKIP_STATEMENTS = ("window hide", "window show", "window auto", "nvl clear",
                   "pause", "pass", "$ renpy.pause", "scene black with",
                   "stop sound", "stop voice")


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def strip_comment(line):
    """去掉行尾注释，但不动字符串里的 #。"""
    out, in_str, i = [], None, 0
    while i < len(line):
        c = line[i]
        if in_str:
            if c == "\\" and i + 1 < len(line):
                out.append(c)
                out.append(line[i + 1])
                i += 2
                continue
            if c == in_str:
                in_str = None
            out.append(c)
        else:
            if c in "\"'":
                in_str = c
                out.append(c)
            elif c == "#":
                break
            else:
                out.append(c)
        i += 1
    return "".join(out).rstrip()


def read_lines(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        return list(enumerate(f.read().splitlines(), 1))


def indent_of(raw):
    return len(raw) - len(raw.lstrip(" \t"))


def unescape(text):
    return (text.replace('\\"', '"').replace("\\n", "\n")
                .replace("\\t", "\t").replace("\\\\", "\\"))


def mdify(text):
    """Ren'Py 的 {} 标记 → STMG 的 Markdown 标记。"""
    text = text.replace("{b}", "**").replace("{/b}", "**")
    text = text.replace("{i}", "*").replace("{/i}", "*")
    text = text.replace("{u}", "").replace("{/u}", "")
    text = re.sub(r'\{color=(#[0-9a-fA-F]{3,8})\}', r'[color=\1]', text)
    text = text.replace("{/color}", "[/color]")
    text = re.sub(r'\{size=(\d+)\}', r'[size=\1]', text)
    text = text.replace("{/size}", "[/size]")
    text = re.sub(r'\{[^{}]*\}', "", text)          # 剩下的标记丢掉
    return text


class Ctx(object):
    def __init__(self, game_dir, out_dir):
        self.game_dir = game_dir
        self.out_dir = out_dir
        self.chars = {}          # 变量名 -> 显示名
        self.images = {}         # "bg airplane" -> 真实相对路径
        self.title = ""
        self.size = "1280x720"
        self.todo = []           # (文件, 行号, 原因, 原文)
        self.stats = Counter()
        self.needed = {}         # out_relative -> abs_src

    def note(self, path, line, why, text):
        self.todo.append((os.path.basename(path), line, why, text.strip()[:80]))

    def tick(self, key, n=1):
        self.stats[key] += n


# --------------------------------------------------------------------------- #
# 素材
# --------------------------------------------------------------------------- #
def find_asset(ctx, name):
    """把 Ren'Py 里的资源名找成真实文件。返回 (out_relative, abs_src)。"""
    if not name:
        return "", ""
    name = name.replace("\\", "/").strip('"')
    if not os.path.splitext(name)[1]:
        return "", ""                      # 没有扩展名，交给调用方报 TODO
    cands = [name]
    if not name.startswith("images/") and not name.startswith("audio/"):
        cands += ["images/" + name, "audio/" + name]
    for rel in cands:
        p = os.path.join(ctx.game_dir, rel)
        if os.path.isfile(p):
            return norm_rel(rel), p
    base = os.path.basename(name).lower()
    for sub in ("images", "audio", ""):
        d = os.path.join(ctx.game_dir, sub) if sub else ctx.game_dir
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.lower() == base:
                rel = (sub + "/" + fn) if sub else fn
                return norm_rel(rel), os.path.join(d, fn)
    return "", ""


def norm_rel(rel):
    """统一落到 images/ 或 audio/ 下面，跟 STMG 项目的习惯保持一致。"""
    rel = rel.replace("\\", "/")
    if rel.startswith(("images/", "audio/")):
        return rel
    ext = os.path.splitext(rel)[1].lower()
    if ext in IMAGE_EXT:
        return "images/" + os.path.basename(rel)
    if ext in AUDIO_EXT:
        return "audio/" + os.path.basename(rel)
    return rel


def asset_of(ctx, path, line, raw):
    rel, src = find_asset(ctx, path)
    if rel:
        ctx.needed[rel] = src
        return rel
    ctx.note(path, line, "找不到素材，路径原样保留", raw)
    return path.replace("\\", "/")


# --------------------------------------------------------------------------- #
# 台词
# --------------------------------------------------------------------------- #
def render_text(ctx, path, line, raw_text, raw_stmt):
    """把 Ren'Py 的字符串字面量转成 STMG 的台词表达式。

    没插值就是 `"……"`；有 [变量] 就拼成 `"前" + 变量 + "后"`。
    """
    body = raw_text.strip()
    if body.startswith('"') and body.endswith('"') and len(body) >= 2:
        body = body[1:-1]
    body = unescape(body)

    parts = re.split(r'(\[[^\[\]]+\])', body)
    pieces = []
    for p in parts:
        if not p:
            continue
        m = re.fullmatch(r'\[([^\[\]]+)\]', p)
        if m and re.fullmatch(r'[A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff.]*', m.group(1)):
            pieces.append(m.group(1))                  # 变量，不加引号
        else:
            pieces.append('"%s"' % mdify(p))
    if not pieces:
        return '""'
    if len(pieces) == 1:
        return pieces[0]
    ctx.tick("插值拼接")
    return " + ".join(pieces)


def split_modifiers(rest):
    """把 `x with fade at right` 拆成 (主体, at 参数)。"""
    at = ""
    m = AT_RE.search(rest)
    if m:
        at = m.group(1).strip()
    cut = MODIFIER.search(rest)
    if cut:
        rest = rest[:cut.start()]
    return rest.strip(), at


def pick_pos(at_raw):
    for token in re.split(r'[,\s]+', at_raw or ""):
        token = token.strip().lower()
        if token in POS_MAP:
            return POS_MAP[token]
    return "center"


# --------------------------------------------------------------------------- #
# 主体转换
# --------------------------------------------------------------------------- #
def body_span(items, i, ind):
    """第 i 行的「块」范围：[i+1, j)，以及块的缩进（没块就是 None）。"""
    j = i + 1
    while j < len(items) and items[j][0] > ind:
        j += 1
    return j, (items[i + 1][0] if j > i + 1 else None)


def conv(items, i, cur_indent, ctx, path):
    out = []
    while i < len(items):
        ind, text, ln = items[i]
        if ind < cur_indent:
            break
        if ind > cur_indent:
            ctx.note(path, ln, "缩进对不上，跳过", text)
            i += 1
            continue
        lines, i = handle(items, i, ind, ctx, path)
        out.extend(lines)
    return out


def handle(items, i, ind, ctx, path):
    text = items[i][1]
    ln = items[i][2]

    # ---- 注释（已在预处理里转好，这里直接输出）----
    if text.startswith("<--"):
        return [text], i + 1

    # ---- label ----
    m = RE_LABEL.match(text)
    if m:
        name = m.group(1)
        # start 不单独出标签：main() 已经在正文开头放了 Start:，
        # 再出一个会变成两个 Start: 标签。
        out = [] if name == "start" else ["%s:" % name]
        j, b_ind = body_span(items, i, ind)
        if b_ind is not None:
            if out:
                out.append("")
            out.extend(conv(items, i + 1, b_ind, ctx, path))
            if out and name != "start":
                out.append("")
        ctx.tick("label")
        return out, j

    # ---- define / image：扫描阶段已经消化掉了，正文里直接扔掉 ----
    if text.startswith("define ") or text.startswith("image "):
        ctx.tick("定义(已消化)")
        return [], i + 1

    # ---- default：变量的初始值 ----
    m = re.match(r'^default\s+([\w\u4e00-\u9fff][\w\u4e00-\u9fff]*)\s*=\s*(.+)$', text)
    if m:
        ctx.tick("变量初值")
        return ["SET %s = %s" % (m.group(1), python_expr(ctx, m.group(2)))], i + 1

    # ---- if / elif / else 链 ----
    if RE_IF.match(text) or RE_ELIF.match(text) or RE_ELSE.match(text):
        chain, idx = [], i
        while True:
            t = items[idx][1]
            m_if, m_el, m_es = RE_IF.match(t), RE_ELIF.match(t), RE_ELSE.match(t)
            cond = m_if.group(1) if m_if else (m_el.group(1) if m_el else None)
            j, b_ind = body_span(items, idx, ind)
            body = conv(items, idx + 1, b_ind, ctx, path) if b_ind is not None else []
            chain.append((cond, body, items[idx][2]))
            idx = j
            if j < len(items) and items[j][0] == ind and \
                    (RE_ELIF.match(items[j][1]) or RE_ELSE.match(items[j][1])):
                continue
            break
        return emit_chain(ctx, chain, ""), idx

    # ---- menu ----
    if RE_MENU.match(text):
        return emit_menu(items, i, ind, ctx, path)

    # ---- scene ----
    if text.startswith("scene ") or text == "scene":
        rest = text[6:].strip()
        if not rest:
            return ["S.cg(\"\")"], i + 1
        name, at = split_modifiers(rest)
        rel = image_path(ctx, name, ln, text)
        ctx.tick("scene")
        return ['S.cg("%s")' % rel], i + 1

    # ---- show ----
    if text.startswith("show "):
        rest = text[5:].strip()
        name, at = split_modifiers(rest)
        rel = image_path(ctx, name, ln, text)
        tag = name.split()[0] if name.split() else "sprite"
        if name.lower().startswith("bg"):
            ctx.tick("show->cg")
            return ['S.cg("%s")' % rel], i + 1
        ctx.tick("show->立绘")
        return ['S.character("%s", pos="%s", tag="%s")'
                % (rel, pick_pos(at), tag)], i + 1

    # ---- hide ----
    if text.startswith("hide "):
        rest = text[5:].strip()
        name, _at = split_modifiers(rest)
        tag = name.split()[0] if name.split() else "sprite"
        ctx.tick("hide")
        return ['S.hide("%s")' % tag], i + 1

    # ---- 音频 ----
    for kw, key in (("play music", "bgm"), ("play sound", "se"),
                    ("play audio", "se"), ("queue music", "bgm")):
        if text.startswith(kw + " "):
            rest = text[len(kw):].strip()
            fname = first_string(rest)
            if not fname:
                ctx.note(path, ln, "音频路径看不懂", text)
                return ["<-- 转换不了：%s -->" % text], i + 1
            rel = asset_of(ctx, fname, ln, text)
            ctx.tick(key)
            if key == "bgm":
                return ['S.play("%s")' % rel], i + 1
            return ['S.sound("%s")' % rel], i + 1

    if text.startswith("stop music") or text.startswith("stop audio"):
        ctx.tick("stop")
        return ['S.stop("bgm")'], i + 1

    if text.startswith("voice "):
        fname = first_string(text[6:])
        rel = asset_of(ctx, fname, ln, text) if fname else ""
        ctx.tick("voice")
        return ['S.voice("%s")' % rel], i + 1

    # ---- 跳转 / 返回 ----
    if text.startswith("jump "):
        ctx.tick("jump")
        return ['S.jump("%s")' % text[5:].strip()], i + 1
    if text in ("return", "return()"):
        ctx.tick("return")
        return ["S.end()"], i + 1

    # ---- $ 语句 ----
    m = RE_SET.match(text)
    if m:
        return handle_python(ctx, path, ln, m.group(1).strip()), i + 1

    # ---- 台词 ----
    stmt = re.sub(r'\s+with\s+[\w.]+$', "", text).strip()
    m = RE_SAY_NAMED.match(stmt)
    if m and m.group("who") in ctx.chars:
        who = ctx.chars[m.group("who")]
        expr = render_text(ctx, path, ln, m.group("text"), text)
        ctx.tick("台词")
        return ['%s%s' % (who, expr)], i + 1
    m = RE_SAY_BARE.match(stmt) or RE_SAY_VERB.match(stmt)
    if m:
        expr = render_text(ctx, path, ln, m.group("text"), text)
        ctx.tick("旁白")
        return [expr], i + 1

    # ---- 明确知道可以忽略的 ----
    low = text.lower()
    for k in SKIP_STATEMENTS:
        if low.startswith(k):
            ctx.tick("忽略(界面/等待)")
            return [], i + 1
    if low == "with" or low.startswith("with "):
        ctx.tick("丢弃(转场)")
        return [], i + 1

    # ---- 真的转不了 ----
    return handle_unknown(items, i, ind, ctx, path, text, ln)


def handle_python(ctx, path, ln, code):
    """$ 后面那一小段 Python。"""
    if "renpy.input" in code or "renpy.input" in code:
        m = re.search(r'renpy\.input\s*\(\s*(.*?)\)\s*$', code)
        prompt = ""
        if m:
            s = first_string(m.group(1))
            prompt = s or ""
        ctx.tick("询问输入")
        return ['STM.Q = "%s"' % mdify(prompt), "Question:"]
    m = RE_ASSIGN.match(code)
    if m:
        name, op, value = m.group(1), m.group(2), m.group(3)
        expr = python_expr(ctx, value)
        if op == "=":
            ctx.tick("变量赋值")
            return ["SET %s = %s" % (name, expr)]
        if op == "+=":
            return ["SET %s = %s + (%s)" % (name, name, expr)]
        if op == "-=":
            return ["SET %s = %s - (%s)" % (name, name, expr)]
        if op == "*=":
            return ["SET %s = %s * (%s)" % (name, name, expr)]
        if op == "/=":
            return ["SET %s = %s / (%s)" % (name, name, expr)]
    ctx.note(path, ln, "$ 语句没看懂", code)
    return ["<-- 转换不了：$ %s -->" % code]


def python_expr(ctx, value):
    """给变量赋值用的表达式做个轻量翻译。"""
    v = value.strip()
    if v in ("True", "true"):
        return "1"
    if v in ("False", "false"):
        return "0"
    if v in ("None", "null"):
        return '""'
    m = re.fullmatch(r'_(?:\("(.*)"\)|\(' r"'(.*)'" r'\))', v)
    if m:
        return '"%s"' % (m.group(1) or m.group(2) or "")
    return v


def handle_unknown(items, i, ind, ctx, path, text, ln):
    """转不了的整块代码，原样注释掉，别让后面的正文被吃掉。"""
    j, b_ind = body_span(items, i, ind)
    head = text.split(":")[0].split()[0] if text.split() else text
    why = {
        "screen": "界面定义，STMG 用 gui.py 画界面",
        "transform": "变换定义，STMG 暂时没有",
        "style": "样式定义，STMG 暂时没有",
        "init": "初始化块（Python）",
        "python": "Python 块",
        "call": "call 子标签，STMG 只有 jump",
        "default": "default 变量（建议改成 SET）",
        "define": "define 定义",
    }.get(head, "没见过的语句")
    ctx.note(path, ln, why, text)
    ctx.tick("无法转换")
    block = [text] + [t for _ind, t, _ln in items[i + 1:j]]
    out = ["<-- 没能转换（%s）：" % why]
    out += ["     " + b for b in block[:6]]
    if len(block) > 6:
        out.append("     ... 还有 %d 行" % (len(block) - 6))
    out.append("-->")
    return out, j


def emit_chain(ctx, chain, pad):
    """if / elif / else 链 → STMG 的 If / Else 嵌套。"""
    out = []
    cond, body, ln = chain[0]
    if cond is None:
        if not body:
            return out
        out.append(pad + "Else:")
        out.extend(pad + "    " + b if b else "" for b in body)
        return out
    if not body:
        ctx.note("", ln, "空分支，已跳过", "If %s" % cond)
        return out
    out.append(pad + "If %s:" % stm_cond(cond))
    out.extend((pad + "    " + b if b else "") for b in body)
    rest = chain[1:]
    if rest:
        out.append(pad + "Else:")
        out.extend(emit_chain(ctx, rest, pad + "    "))
    return out


def stm_cond(cond):
    """Ren'Py 的条件 → STMG 的条件。"""
    c = cond.strip()
    if c in ("True", "true"):
        return "1"
    if c in ("False", "false"):
        return "0"
    return c


def emit_menu(items, i, ind, ctx, path):
    j, b_ind = body_span(items, i, ind)
    body = items[i + 1:j]
    ln = items[i][2]

    caption, options = "", []
    k = 0
    while k < len(body):
        cind, ctext, cln = body[k]
        if cind != b_ind:
            k += 1
            continue
        m = RE_OPTION.match(ctext)
        if m:
            cap = m.group("cap")
            if m.group("cond"):
                ctx.note(path, cln, "选项带 if 条件，已忽略条件",
                         "if %s" % m.group("cond"))
            end = k + 1
            while end < len(body) and body[end][0] > cind:
                end += 1
            sub = [(x[0], x[1], x[2]) for x in body[k + 1:end]]
            options.append((cap, sub, cln))
            k = end
            continue
        m2 = RE_SAY_BARE.match(ctext.strip())
        if m2 and not caption:
            caption = ctext.strip().strip('"')
            k += 1
            continue
        ctx.note(path, cln, "menu 里没看懂的语句", ctext)
        k += 1

    if not options:
        ctx.note(path, ln, "menu 里没有解析出选项", items[i][1])
        return [], j

    out = []
    if caption:
        out.append('"%s"' % mdify(caption))
        out.append("")
    out.append("Choose:")
    for cap, _sub, _cl in options:
        out.append('    "%s"' % mdify(cap))
    out.append("")
    for cap, sub, cln in options:
        out.append('If "%s":' % mdify(cap))
        if sub:
            sub_ind = sub[0][0]
            body_out = conv(sub, 0, sub_ind, ctx, path)
            if not body_out:
                body_out = ['"（这个选项在原剧本里没有内容）"']
            out.extend("    " + b if b else "" for b in body_out)
        else:
            out.append('    "（这个选项在原剧本里没有内容）"')
        out.append("")
    ctx.tick("选择支", len(options))
    return out, j


def image_path(ctx, name, ln, raw):
    """把 Ren'Py 的图名（bg airplane / kongjie normal）换成真实路径。"""
    key = " ".join(name.split())
    if key in ctx.images:
        return asset_of(ctx, ctx.images[key], ln, raw)
    direct, src = find_asset(ctx, key)
    if direct:
        ctx.needed[direct] = src
        return direct
    ctx.note("", ln, "图名没在 image 定义里，也没找到同名文件", raw)
    return key


def first_string(text):
    m = RE_STR.search(text or "")
    if not m:
        return ""
    return unescape(m.group(0)[1:-1])


# --------------------------------------------------------------------------- #
# 预处理 / 主流程
# --------------------------------------------------------------------------- #
def build_items(path, ctx):
    """读取一个 .rpy，去掉注释/空行，转成 [(缩进, 语句, 行号)]。"""
    items = []
    for ln, raw in read_lines(path):
        if not raw.strip():
            continue
        code = strip_comment(raw)
        if not code.strip():
            stripped = raw.strip()
            if stripped.startswith("#"):
                items.append((indent_of(raw), "<-- %s -->" % stripped[1:].strip(), ln))
                ctx.tick("注释")
            continue
        items.append((indent_of(code), code.rstrip().strip(), ln))
    return items


def scan_meta(path, ctx):
    """只看标题和分辨率，不看角色/图像。"""
    if not os.path.isfile(path):
        return
    for _ln, raw in read_lines(path):
        t = strip_comment(raw).strip()
        m = RE_DEF_NAME.match(t)
        if m and not ctx.title:
            ctx.title = m.group(1)
        m = RE_GUI_INIT.search(t)
        if m:
            ctx.size = "%sx%s" % (m.group(1), m.group(2))


def scan_defs(path, ctx):
    for ln, raw in read_lines(path):
        t = strip_comment(raw).strip()
        if not t:
            continue
        m = RE_DEF_CHAR.match(t)
        if m:
            args = m.group(2)
            s = first_string(args)
            ctx.chars[m.group(1)] = s or m.group(1)
            continue
        m = RE_DEF_NAME.match(t)
        if m and not ctx.title:
            ctx.title = m.group(1)
            continue
        m = RE_GUI_INIT.search(t)
        if m:
            ctx.size = "%sx%s" % (m.group(1), m.group(2))
            continue
        m = RE_IMAGE.match(t)
        if m:
            ctx.images[" ".join(m.group(1).split())] = m.group(2)
            continue


def rpy_files(game_dir, extra):
    out = []
    for fn in sorted(os.listdir(game_dir)):
        if not fn.endswith(".rpy"):
            continue
        if fn in ENGINE_RPY and fn not in extra:
            continue
        out.append(os.path.join(game_dir, fn))
    return out


def copy_assets(ctx):
    n = 0
    total = 0
    for rel, src in sorted(ctx.needed.items()):
        dst = os.path.join(ctx.out_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copy2(src, dst)
        n += 1
        total += os.path.getsize(src)
    return n, total


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, u)
        n /= 1024.0
    return "%.1f TB" % n


def main(argv):
    args = argv[1:]
    if not args:
        print(__doc__)
        return 2
    game_dir = os.path.abspath(args[0])
    out_dir = None
    title = None
    size = None
    do_assets = True
    extra = set()

    i = 1
    while i < len(args):
        a = args[i]
        if a == "--out":
            i += 1
            out_dir = args[i]
        elif a == "--title":
            i += 1
            title = args[i]
        elif a == "--size":
            i += 1
            size = args[i]
        elif a == "--no-assets":
            do_assets = False
        elif a == "--include":
            i += 1
            extra.add(os.path.basename(args[i]))
        i += 1

    if not os.path.isdir(game_dir):
        print("找不到游戏目录：%s" % game_dir)
        return 2

    name = os.path.basename(os.path.dirname(game_dir)) or "renpy_game"
    out_dir = os.path.abspath(out_dir or os.path.join(ROOT, "projects", name))
    os.makedirs(out_dir, exist_ok=True)

    ctx = Ctx(game_dir, out_dir)
    files = rpy_files(game_dir, extra)
    if not files:
        print("这个目录里没有可转换的 .rpy")
        return 2

    print("游戏目录：%s" % game_dir)
    print("剧本文件：%s" % ", ".join(os.path.basename(f) for f in files))
    print("输出到　：%s" % out_dir)
    print("-" * 56)

    # 标题和分辨率在 options.rpy / gui.rpy 里，那两个文件不参与转换但要读
    for meta in ("options.rpy", "gui.rpy"):
        scan_meta(os.path.join(game_dir, meta), ctx)
    for f in files:
        scan_defs(f, ctx)
    print("角色 %d 个 · 图像定义 %d 个 · 分辨率 %s"
          % (len(ctx.chars), len(ctx.images), ctx.size))

    body = []
    for f in files:
        items = build_items(f, ctx)
        if not items:
            continue
        body.append("<-- ===== 来自 %s ===== -->" % os.path.basename(f))
        body.extend(conv(items, 0, 0, ctx, f))
        body.append("")

    title = title or ctx.title or name
    size = size or ctx.size

    head = ["<",
            "Size=%s" % size,
            'title="%s"' % title,
            'Ver="1.0.0"',
            'Pack="com.example.%s"' % re.sub(r"\W+", "", name).lower()[:24],
            'Lang="cn"',
            'Font="Microsoft YaHei"',
            ">",
            "<",
            "Start:",
            ""]

    lines = head + [l for l in body] + [">", "<", '"感谢游玩"', ">", ""]
    script_path = os.path.join(out_dir, "script.stm")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    key = "stmg-%s-%d" % (re.sub(r"\W+", "", name).lower() or "game",
                          int(time.time()) % 100000)
    with open(os.path.join(out_dir, "options.stm"), "w", encoding="utf-8") as f:
        f.write('<\n'
                'About = "%s —— 由 Ren\'Py 工程自动转换而来。"\n'
                'Enc = "%s"\n'
                'dec = "*.stm,*.png,*.jpg,*.mp3,*.ogg,*.wav"\n'
                'AllowNet = "false"\n'
                '>\n' % (title, key))

    if do_assets:
        n, total = copy_assets(ctx)
        print("素材　　：复制 %d 个文件，%s" % (n, human(total)))
    else:
        print("素材　　：已跳过（--no-assets）")

    # 报告
    todo = os.path.join(out_dir, "转换报告.md")
    with open(todo, "w", encoding="utf-8") as f:
        f.write("# Ren'Py → STMG 转换报告\n\n")
        f.write("来源：`%s`\n\n" % game_dir)
        f.write("输出：`%s`\n\n" % out_dir)
        f.write("## 转换统计\n\n| 项目 | 数量 |\n|---|---|\n")
        for k, v in ctx.stats.most_common():
            f.write("| %s | %d |\n" % (k, v))
        f.write("| 角色 | %d |\n" % len(ctx.chars))
        f.write("| 图像定义 | %d |\n\n" % len(ctx.images))
        f.write("## 需要手工处理的\n\n")
        if not ctx.todo:
            f.write("没有。全部转换成功。\n")
        else:
            f.write("| 文件 | 行 | 原因 | 原文 |\n|---|---|---|---|\n")
            for fn, ln, why, text in ctx.todo:
                f.write("| %s | %d | %s | `%s` |\n"
                        % (fn, ln, why, text.replace("|", "\\|")))
        f.write("\n## 已知差异\n\n")
        f.write("- Ren'Py 的转场（`with fade` / `dissolve`）STMG 目前没有，"
                "已全部丢弃\n")
        f.write("- `screen` / `transform` / `style` 这些界面定义不会转换，"
                "STMG 的界面在 `gui.py`\n")
        f.write("- 立绘位置只认 `at left` / `at right` / `at center`，"
                "其余位置按 center 处理\n")

    print("-" * 56)
    print("剧本　　：%s" % script_path)
    if ctx.todo:
        print("要手工处理 %d 处，清单见 转换报告.md" % len(ctx.todo))
    else:
        print("全部转换成功，没有遗留。")

    # 顺手做一次语法检查
    sys.path.insert(0, ROOT)
    try:
        from stmg import parser
        sc = parser.parse_file(script_path)
        print("语法检查：%d 个错误，%d 条提示"
              % (sc.error_count(), len(sc.issues) - sc.error_count()))
        for it in sc.issues[:8]:
            print("   %s" % it)
    except Exception as e:                             # noqa: BLE001
        print("语法检查没跑起来：%s" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
