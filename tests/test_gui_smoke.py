# -*- coding: utf-8 -*-
"""界面冒烟测试：新增的几块 UI（调试覆盖层 / 章节目录 / 按键设置 / 镜头 / 转场）
在无头环境里能不能画出来。

不是视觉测试 —— 只保证「点开不炸、画一帧不抛异常」。
真正的观感还是得人眼看着调，这里挡的是 KeyError / AttributeError 这类硬崩。
"""

import pygame
import pytest

from stmg import gui, parser

HEAD = """<
Size=1280x720
title="界面测试"
>
<
Start:
S.cg("bg/room.png")
"第一句"
S.jump("第二章")

第二章:
"第二章开始了"
S.end()
>
"""


@pytest.fixture
def app(project):
    """建一局无头游戏：返回 App，跑完把窗口关掉。"""
    _, write = project
    sc = parser.parse_file(write(HEAD))
    assert sc.error_count() == 0, [str(i) for i in sc.issues]
    a = gui.App(sc, None, True)
    yield a
    a.running = False
    pygame.display.quit()


def test_title_and_first_frame(app):
    """标题界面能画，进游戏后第一句也能画。"""
    app.draw()
    app.start_game()
    app.draw()
    assert app.state in (gui.ADVANCE, gui.CHOOSE, gui.QUESTION, gui.WAIT)


def test_debug_overlay_draws(app):
    """调试覆盖层：开关一次、画一帧，不能因为变量表为空就崩。"""
    app.start_game()
    app.debug = True
    app.draw()
    app.debug = False
    app.draw()


def test_chapter_menu(app):
    """章节目录能收集标签、能画、点一个能跳过去。"""
    assert app.chapters, "没有收集到任何章节（Start / 第二章）"
    app.open_chapters()
    app.draw()
    assert app.state == gui.CHAPTER


def test_keybind_panel(app):
    """按键设置面板能开能画，改键后 keymap 真的变了。"""
    app.open_keybind()
    app.draw()
    assert app.state == gui.KEYBIND
    old = app._key("replay_voice")
    app.settings.keymap["replay_voice"] = pygame.K_F8
    assert app._key("replay_voice") == pygame.K_F8
    app.settings.keymap["replay_voice"] = old


def test_camera_and_transition_frames(app):
    """镜头缩放 / 震屏 / 转场同时生效时，每帧都能画完。"""
    app.start_game()
    app._apply_camera({"mode": "zoom", "zoom": 1.25, "dur": 0.2})
    app.update(0.05)
    app.draw()
    app._apply_camera({"mode": "shake", "amp": 6, "dur": 0.1})
    app.update(0.05)
    app.draw()
    app.transition = {"kind": "wipe", "t": 0.05, "dur": 0.2}
    app.draw()


def test_replay_voice_without_voice(app):
    """这句没有语音时点重听：只提示，不崩。"""
    app.start_game()
    app.replay_voice()


def test_replay_button_appears_with_voice(app):
    """有语音时对话框右下角要出现「重听」按钮，并且矩形落在对话框里。"""
    app.start_game()
    app.audio.last_voice = "voice/001.wav"      # 只影响「有没有按钮」，不真播
    app.draw()
    assert app.replay_rect is not None, "有语音却没画重听按钮"
    assert app.box_rect().contains(app.replay_rect)


def test_start_game_from_chapter(app):
    """章节选择点「第二章」要真的从那一节开始，而不是从第一句重头放。"""
    app.start_game("第二章")
    assert "第二章开始了" in (app.session.text or "")


def test_question_panel_with_validation(app):
    """询问框：整数模式 + 校验错误时也要能画（红字提示不能把排版撑坏）。"""
    app.start_game()
    app.state = gui.QUESTION
    app.session.block = {"t": "question", "prompt": "年龄？", "qtype": "int",
                         "qmin": 1, "qmax": 99}
    app.qtype, app.qmin, app.qmax, app.qmaxlen = "int", 1, 99, None
    app.input_text, app.q_error = "12", ""
    app.draw()
    app.q_error = "不能大于 99"
    app.draw()
