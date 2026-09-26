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

# 内联标记的正则。用命名分组（?P<xxx>）把每种标记分开，下面 render() 里
# 按「哪个分组捕获到了」判断这是哪种标记——排在前面的优先匹配。
#   color   [color=#ff5555]红[/color]   改颜色（#rgb/#rrggbb 或英文色名）
#   size    [size=20]大[/size]          改字号
#   ruby    注音：{ruby:汉字|かんじ}    生僻字/角色名的假名注音（兼容「注音:」写法）
#   bold    **粗**                      粗体
#   strike  ~~删~~                      删除线
#   code    `等宽`                      等宽字体（代码感）
#   italic  *斜*                        斜体（左右不能是 *，避免和 ** 粗体打架）
# re.S 让 . 也能匹配换行，标记可跨行。
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

    每个 run（一段「同款样式」的文字）长这样：
        {"t": 文本, "bold": bool, "italic": bool,
         "strike": bool, "code": bool, "color": None|str, "size": None|int}
    同一次出现的样式叠加（比如 **红字** 同时 bold=True 且 color 有值），
    怎么画交给 gui.py——这里只负责「识别和切段」，不碰绘制。

    做法：pos 记下「上次处理到的位置」，每匹配到一个标记，先把 pos 到标记
    开头之间的纯文本塞一段，再处理标记本身，最后把 pos 推到标记末尾；
    循环结束若还有剩，把尾巴当纯文本收掉。
    """
    # 一段文本的「默认样式模板」，每个 run 都从它拷贝再改个别字段
    base = {"t": "", "bold": False, "italic": False,
            "strike": False, "code": False, "color": None, "size": None}
    runs, pos = [], 0
    for m in TOKEN_RE.finditer(text):
        # 标记前面的纯文本（没有标记的部分），单独成一段
        if m.start() > pos:
            runs.append(dict(base, t=text[pos:m.start()]))
        pos = m.end()
        # 按「哪个命名分组命中」分流；同时命中也只走第一个非 None 的分支
        if m.group("colortext") is not None:
            # 改颜色：color 记下色值，文字本身照原样
            runs.append(dict(base, t=m.group("colortext"), color=m.group("color")))
        elif m.group("sizetext") is not None:
            # 改字号：size 捕获的是字符串，转成 int 用
            runs.append(dict(base, t=m.group("sizetext"), size=int(m.group("size"))))
        elif m.group("rbase") is not None:
            # 注音：正文用汉字，后面跟一段灰色小号假名（用括号包起来）
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
    # 收尾：最后一个标记之后如果还有纯文本，补一段
    if pos < len(text):
        runs.append(dict(base, t=text[pos:]))
    # 丢掉空段（两个相邻标记之间什么都没写），避免 gui 画空 run
    return [r for r in runs if r["t"] != ""]


def plain(text):
    """去掉所有 md 标记，得到纯文本（给打字机效果 / 历史记录用）。"""
    return "".join(r["t"] for r in render(text))


def strip_quotes(text):
    """剥掉文本首尾的英文双引号（剧本里字符串字面量常写成 "xxx"）。

    只在外层成对是 " 时才剥；只有一个或不是引号则原样返回。
    """
    t = text.strip()
    # 至少两个字符、且首末都是 " 才认为是被引号包住，去掉这两层
    if len(t) >= 2 and t[0] == '"' and t[-1] == '"':
        return t[1:-1]
    return t
