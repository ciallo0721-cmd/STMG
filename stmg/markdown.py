# -*- coding: utf-8 -*-
"""STMG 的 Markdown 内联渲染模块。

设计稿里只写了「"**hello**"加粗」+「就是把 md 的特性加入到制作 galgame 中」，
所以这里先支持最常用的一小撮，够用且好扩展：

    **粗体**   *斜体*   ~~删除线~~   `等宽`
    [color=#ff5555]红色[/color]
    [size=20]字号[/size]
    {ruby:汉字|かんじ}          —— 注音（给角色名/生僻字用）

输出「run 列表」，交给 gui.py 决定怎么画。
"""

import re

TOKEN_RE = re.compile(
    r"\[color=(?P<color>#[0-9a-fA-F]{3,8}|[A-Za-z]+)\](?P<colortext>.*?)\[/color\]"
    r"|\[size=(?P<size>\d+)\](?P<sizetext>.*?)\[/size\]"
    r"|\{(?:ruby|注音):(?P<rbase>[^|]+)\|(?P<rtext>[^}]+)\}"
    r"|\*\*(?P<bold>.+?)\*\*"
    r"|~~(?P<strike>.+?)~~"
    r"|`(?P<code>[^`]+)`"
    r"|(?<!\*)\*(?P<italic>[^*]+)\*(?!\*)",
    re.S,
)


def render(text):
    """把一段带 md 标记的文本切成 run 列表。

    每个 run: {"t": 文本, "bold": bool, "italic": bool,
               "strike": bool, "code": bool, "color": None|str, "size": None|int}
    """
    base = {"t": "", "bold": False, "italic": False,
            "strike": False, "code": False, "color": None, "size": None}
    runs, pos = [], 0
    for m in TOKEN_RE.finditer(text):
        if m.start() > pos:
            runs.append(dict(base, t=text[pos:m.start()]))
        pos = m.end()
        if m.group("colortext") is not None:
            runs.append(dict(base, t=m.group("colortext"), color=m.group("color")))
        elif m.group("sizetext") is not None:
            runs.append(dict(base, t=m.group("sizetext"), size=int(m.group("size"))))
        elif m.group("rbase") is not None:
            runs.append(dict(base, t=m.group("rbase")))
            runs.append(dict(base, t="(%s)" % m.group("rtext"), size=10, color="#888888"))
        elif m.group("bold") is not None:
            runs.append(dict(base, t=m.group("bold"), bold=True))
        elif m.group("strike") is not None:
            runs.append(dict(base, t=m.group("strike"), strike=True))
        elif m.group("code") is not None:
            runs.append(dict(base, t=m.group("code"), code=True))
        elif m.group("italic") is not None:
            runs.append(dict(base, t=m.group("italic"), italic=True))
    if pos < len(text):
        runs.append(dict(base, t=text[pos:]))
    return [r for r in runs if r["t"] != ""]


def plain(text):
    """去掉所有 md 标记，得到纯文本（给打字机效果 / 历史记录用）。"""
    return "".join(r["t"] for r in render(text))


def strip_quotes(text):
    t = text.strip()
    if len(t) >= 2 and t[0] == '"' and t[-1] == '"':
        return t[1:-1]
    return t
