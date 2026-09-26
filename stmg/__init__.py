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

# ---- 错误与诊断（被其它模块大量复用，这里直接暴露到顶层）----
#   STMFatal  致命错误类：抛出后整个解析/运行会中断
#   Issue     非致命问题（解析警告/报错），带 行号 + 中文说明，给作者看
#   level_name 把 Issue 的级别数字转成 "错误"/"警告" 等中文名
from .errors import STMFatal, Issue, level_name       # noqa: F401
# ---- 剧本解析（输入侧）----
#   Script       解析后的剧本对象（语句树 + 资源表）
#   parse_file   从 .stm 文件解析
#   parse_text   从内存里的字符串解析（测试/内嵌用）
from .parser import Script, parse_file, parse_text    # noqa: F401
# ---- 运行核心：把剧本语句跑成「事件流」----
from .runtime import Runtime                          # noqa: F401
# ---- 会话层：推进事件、管存读档、对接界面 ----
from .session import Session                          # noqa: F401

# 引擎版本号（setup / 报错界面会展示）。
__version__ = "1.0.0"
