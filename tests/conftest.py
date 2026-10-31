# -*- coding: utf-8 -*-
"""pytest 公共骨架：把仓库根塞进 sys.path，并把 pygame 切到无头模式。

为什么要有这个文件：引擎在 import pygame 时就会初始化显示模块（gui.renderer 里），
CI 上没有显示器，不设 SDL_VIDEODRIVER=dummy 会直接 "No available video device"。
放 conftest 而不是每个测试里设，是因为 import 顺序不受控。
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest  # noqa: E402


@pytest.fixture
def project(tmp_path):
    """造一个最小的「项目目录」：返回 (目录, 剧本路径)。

    引擎把剧本所在目录当 root（存档 / 美化包都挂在它下面），
    所以测试里必须用真实文件路径，不能只喂字符串。
    """
    d = tmp_path / "proj"
    d.mkdir()

    def write(text, name="script.stm"):
        p = d / name
        p.write_text(text, encoding="utf-8")
        return str(p)

    return str(d), write
