# -*- coding: utf-8 -*-
"""Session 回归测试：读档重放不能在副作用 / 演出事件上停住。

第 3 期加转场时就踩过这个坑：`transition` 不是状态改动的副作用，
但它在「重放」时同样不该拦住推进，否则读档会停在换场那一拍。
"""

from stmg import parser, session

HEAD = """<
Size=1280x720
title="会话测试"
>
<
Start:
"""


def build(project, body):
    _, write = project
    sc = parser.parse_file(write(HEAD + body + "\n>\n"))
    assert sc.error_count() == 0, [str(i) for i in sc.issues]
    return sc


def test_reset_skips_transition_and_wait(project):
    """target_say=2 时应该正好停在第二句，别被前面的转场 / wait 挡住。"""
    sc = build(project, (
        '"第一句"\n'
        'S.transition("wipe", dur=0.3)\n'
        "S.wait(1.0)\n"
        '"第二句"\n'
        '"第三句"\n'
    ))
    sess = session.Session(sc, None, True)
    blk = sess.reset(target_say=2)
    assert blk["t"] == "say"
    assert "第二句" in blk["text"], blk


def test_scene_restored_from_replay(project):
    """重放要把场景副作用重新吃一遍（背景 / 立绘不能丢）。"""
    sc = build(project, (
        'S.cg("bg/a.png")\n'
        '"一句"\n'
        'S.cg("bg/b.png")\n'
        '"两句"\n'
    ))
    sess = session.Session(sc, None, True)
    sess.reset(target_say=2)
    assert sess.scene["bg"].endswith("bg/b.png"), sess.scene["bg"]
