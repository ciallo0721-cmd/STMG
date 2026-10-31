# -*- coding: utf-8 -*-
"""解析器回归测试：语法树结构、条件、include、Call/Return。

这些是「老剧本必须继续能跑」的底线，改 parser 时先跑这一组。

注意剧本的物理结构：头部信息和正文各在一个 < ... > 块里，
正文块里还要有 Start: 入口 —— 少了任一层，parser 都会判定「正文是空的」。
"""

from stmg import parser

HEAD = """<
Size=1280x720
title="测试剧本"
>
<
Start:
"""


def script(body):
    """把正文包进剧本块，省得每个用例都手写 < > 和 Start:。"""
    return HEAD + body + "\n>\n"


def kinds(sc, k):
    """数一数整棵树里某种语句出现几次。"""
    return len([s for s in sc.walk() if s["k"] == k])


def test_basic_parse_no_errors(project):
    """最小剧本能解析，且标题 / 分辨率读对。"""
    _, write = project
    sc = parser.parse_file(write(script('"第一句"\n"第二句"\n')))
    assert sc.error_count() == 0, [str(i) for i in sc.issues]
    assert sc.size == (1280, 720)
    assert sc.title == "测试剧本"
    assert kinds(sc, "say") == 2


def test_if_else_and_nested(project):
    """If / Else / 嵌套 If 都解析成正确的结构，别被缩进带偏。"""
    _, write = project
    body = (
        "SET 好感度 = 0\n"
        "If 好感度 >= 10:\n"
        '    "高"\n'
        "    If 好感度 > 50:\n"
        '        "很高"\n'
        "    EndIf\n"
        "Else:\n"
        '    "低"\n'
        "EndIf\n"
    )
    sc = parser.parse_file(write(script(body)))
    assert sc.error_count() == 0, [str(i) for i in sc.issues]
    conds = [s["cond"] for s in sc.walk() if s["k"] == "if"]
    assert "好感度 >= 10" in conds
    assert "好感度 > 50" in conds
    outer = [s for s in sc.walk() if s["k"] == "if" and s["cond"].strip() == "好感度 >= 10"][0]
    assert outer["else_body"], "外层 If 的 else 分支丢了"


def test_compound_condition_is_kept(project):
    """复合条件原样保留（求值在 runtime，parser 不该自作聪明地拆分）。"""
    _, write = project
    body = (
        "SET 好感度 = 30\n"
        "If 好感度 >= 10 and 好感度 < 50:\n"
        '    "中间"\n'
        "EndIf\n"
    )
    sc = parser.parse_file(write(script(body)))
    assert sc.error_count() == 0, [str(i) for i in sc.issues]
    conds = [s["cond"] for s in sc.walk() if s["k"] == "if"]
    assert "and" in conds[0]


def test_include_inlines_body(project):
    """include 是解析期内联：被包含文件里的台词要出现在主树里。"""
    d, write = project
    with open(d + "/extra.stm", "w", encoding="utf-8") as f:
        # 被 include 的文件同样要包在 < ... > 里
        f.write('<\n"来自被包含的文件"\n>\n')
    sc = parser.parse_file(write(script('include "extra.stm"\n"主线台词"\n')))
    assert sc.error_count() == 0, [str(i) for i in sc.issues]
    texts = [str(s["text"]) for s in sc.walk() if s["k"] == "say"]
    assert any("被包含" in t for t in texts), texts


def test_call_return_parsed(project):
    """Call / Return 解析成 call_sub + return，且能定位到标签。"""
    _, write = project
    body = (
        'Call "小段"\n'
        '"调用之后"\n'
        "S.end()\n"
        "\n"
        "小段:\n"
        '"子程序里"\n'
        "Return\n"
    )
    sc = parser.parse_file(write(script(body)))
    assert sc.error_count() == 0, [str(i) for i in sc.issues]
    assert kinds(sc, "call_sub") == 1
    assert kinds(sc, "return") == 1
    labels = [s["name"] for s in sc.walk() if s["k"] == "label"]
    assert "小段" in labels and "Start" in labels


def test_syntax_error_reported(project):
    """引用了不存在的文件必须报错——否则发布出去才发现缺章节。"""
    _, write = project
    sc = parser.parse_file(write(script('include "不存在的文件.stm"\n"继续"\n')))
    assert sc.error_count() > 0
    assert any(("不存在" in str(i)) or ("找不到" in str(i)) for i in sc.issues), \
        [str(i) for i in sc.issues]


def test_missing_endif_is_tolerated(project):
    """缺 EndIf 时 parser 会把后续行都当正文（不报错）——这是现状，先锁住行为。

    这条不是「应该这样」，而是提醒：改缩进 / 块解析时别悄悄改变这个宽容度。
    """
    _, write = project
    sc = parser.parse_file(write(script('If 1 == 1:\n    "只有 If 没有 EndIf"\n')))
    assert sc.error_count() == 0
    assert kinds(sc, "if") == 1
