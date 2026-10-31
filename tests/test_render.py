# -*- coding: utf-8 -*-
"""渲染层测试：转场不崩、自定义转场能加载、坏的自定义不拖垮引擎。

只用到 pygame 的 Surface，不建窗口（conftest 已经把 SDL 设成 dummy）。
"""

import os

import pygame

from stmg import render

W, H = 320, 180
KINDS = ("fade", "dissolve", "flash", "slide_left", "slide_right",
         "slide_up", "slide_down", "wipe", "zoom", "iris")


def surface(color=(40, 60, 90)):
    """造一块纯色画布，当作「新的一帧」。"""
    s = pygame.Surface((W, H))
    s.fill(color)
    return s


def test_all_builtin_transitions_dont_crash():
    """每个内置转场在 0 / 0.25 / 0.5 / 0.75 / 1 五个进度点都必须能画完。"""
    prev = surface((200, 30, 40))
    for kind in KINDS:
        for p in (0.0, 0.25, 0.5, 0.75, 1.0):
            surf = surface()
            render.draw_transition(surf, kind, p, W, H, (16, 16, 22), prev)
    # 未知名字不能炸，按 fade 处理
    render.draw_transition(surface(), "根本没有这个转场", 0.5, W, H, (0, 0, 0), prev)


def test_fade_masks_at_midpoint():
    """fade 在中点最黑 —— 这是「换景那一瞬间观众看不到跳帧」的关键。"""
    surf = surface((255, 255, 255))
    render.draw_transition(surf, "fade", 0.5, W, H, (0, 0, 0), surface((255, 255, 255)))
    r, g, b = surf.get_at((W // 2, H // 2))[:3]
    assert r < 40 and g < 40 and b < 40, (r, g, b)


def test_custom_transitions_load_and_apply(project):
    """custom/transitions.py 里的 TRANSITIONS 能被加载，并且真的被调用。"""
    d, _ = project
    os.makedirs(os.path.join(d, "custom"))
    path = os.path.join(d, "custom", "transitions.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "import pygame\n"
            "def red_flash(surface, prev, p, w, h):\n"
            "    m = pygame.Surface((w, h))\n"
            "    m.fill((255, 0, 0))\n"
            "    m.set_alpha(120)\n"
            "    surface.blit(m, (0, 0))\n"
            "TRANSITIONS = {'red_flash': red_flash}\n"
        )
    table = render.load_custom_transitions(d)
    assert "red_flash" in table

    surf = surface((0, 0, 0))
    render.draw_transition(surf, "red_flash", 0.5, W, H, (0, 0, 0), None, table)
    r, g, b = surf.get_at((W // 2, H // 2))[:3]
    assert r > 60 and g < 40 and b < 40, (r, g, b)


def test_broken_custom_transition_falls_back(project):
    """自定义转场抛异常时必须退回内置效果，不能让整局游戏崩掉。"""
    d, _ = project
    os.makedirs(os.path.join(d, "custom"))
    with open(os.path.join(d, "custom", "transitions.py"), "w", encoding="utf-8") as f:
        f.write(
            "def boom(surface, prev, p, w, h):\n"
            "    raise RuntimeError('故意炸的')\n"
            "TRANSITIONS = {'boom': boom}\n"
        )
    table = render.load_custom_transitions(d)
    surf = surface((255, 255, 255))
    render.draw_transition(surf, "boom", 0.5, W, H, (0, 0, 0), None, table)
    # 退回 fade：中点应该被压暗了
    r, _, _ = surf.get_at((W // 2, H // 2))[:3]
    assert r < 60, r


def test_broken_custom_file_returns_empty(project):
    """transitions.py 语法错 / 没有 TRANSITIONS，都只返回空表，不该抛异常。"""
    d, _ = project
    os.makedirs(os.path.join(d, "custom"))
    with open(os.path.join(d, "custom", "transitions.py"), "w", encoding="utf-8") as f:
        f.write("this is not python(((\n")
    assert render.load_custom_transitions(d) == {}
    assert render.load_custom_transitions(os.path.join(d, "没有这个目录")) == {}
