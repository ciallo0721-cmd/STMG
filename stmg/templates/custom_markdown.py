# -*- coding: utf-8 -*-
"""自定义内联标记 —— 想让剧本支持自己的写法，就改这里。

引擎本来支持这些（写在台词里）：

    **粗体**      *斜体*      ~~删除线~~      `等宽`
    [color=#ff88bb]文字[/color]
    [size=28]文字[/size]
    {ruby:汉字|かんじ}

本文件里的 render(text) 会**替换**引擎的实现：

    text   —— 一句台词（已经去掉外层引号、算过变量拼接）
    返回   —— run 列表，每个 run 是一个字典：
              {"t": 文字, "bold": 粗体, "italic": 斜体, "strike": 删除线,
               "code": 等宽, "color": None 或 "#rrggbb", "size": None 或整数}

最简单的用法就是先用引擎的实现，自己再加规则：

    from stmg import markdown as _md

    def render(text):
        text = text.replace("[w]", "……")      # 先把自定义标记处理掉
        return _md.render(text)                # 剩下的交给引擎

注意：
  * 别 import stmg.gui —— 那个模块要 pygame，在外面跑会炸；
  * plain() 是打字机和历史记录用的纯文本，不写就直接用 render 的结果拼；
  * 改坏了也不会崩游戏，语法错误会在「历史记录」旁边以提示形式显示（开发模式）。
"""

from stmg import markdown as _md


def render(text):
    """默认行为 = 引擎原样。想加规则就在 return 之前动手。"""
    return _md.render(text)


def plain(text):
    """纯文本（打字机、历史记录用）。"""
    return "".join(r["t"] for r in render(text))
