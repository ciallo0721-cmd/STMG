# -*- coding: utf-8 -*-
"""STMG —— Super Text Markdown Galgame engine.

一个把剧本和引擎分开的视觉小说引擎：
parser 负责把 .stm 解析成语句树，Runtime 把它跑成事件流，
Session 管推进和存读档，gui 负责画出来。中间几层都不依赖 pygame。

常用入口：

    from stmg import parser, Session
    script = parser.parse_file("script.stm")
    s = Session(script)
"""

from .errors import STMFatal, Issue, level_name       # noqa: F401
from .parser import Script, parse_file, parse_text    # noqa: F401
from .runtime import Runtime                          # noqa: F401
from .session import Session                          # noqa: F401

__version__ = "1.0.0"
