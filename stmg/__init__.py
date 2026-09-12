# -*- coding: utf-8 -*-
"""STMG —— Super Text Markdown Galgame engine.

设计：ciallo0721-cmd
实现：WorkBuddy（塔菲喵）

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
