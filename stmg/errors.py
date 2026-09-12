# -*- coding: utf-8 -*-
"""STMG 的错误体系。

设计稿定的五级命名原样保留：

    A error        1 个
    An error       2 ~ 39 个
    Many error     40 ~ 49 个
    Lot of error   50 ~ 99 个
    Bro....        100 个以上
"""

import os
import traceback


def level_name(n):
    if n <= 0:
        return None
    if n == 1:
        return "A error"
    if n < 40:
        return "An error"
    if n < 50:
        return "Many error"
    if n < 100:
        return "Lot of error"
    return "Bro...."


class Issue(object):
    """一条语法 / 运行时问题。level 取 'error' 或 'warn'。"""

    def __init__(self, line, message, hint="", level="error"):
        self.line = line
        self.message = message
        self.hint = hint
        self.level = level

    def __str__(self):
        pos = "行 %d" % self.line if self.line else "全局"
        s = "[%s] %s" % (pos, self.message)
        if self.hint:
            s += "  -> " + self.hint
        return s


class STMFatal(Exception):
    """跑不下去了，必须停机。"""

    def __init__(self, message, line=None):
        Exception.__init__(self, message)
        self.message = message
        self.line = line

    def __str__(self):
        if self.line:
            return "行 %s: %s" % (self.line, self.message)
        return self.message


class ErrorBag(object):
    """收集一次运行里的所有问题。"""

    def __init__(self, path=""):
        self.path = path
        self.issues = []

    def add(self, line, message, hint="", level="error"):
        self.issues.append(Issue(line, message, hint, level))

    def warn(self, line, message, hint=""):
        self.issues.append(Issue(line, message, hint, "warn"))

    def extend(self, issues):
        self.issues.extend(issues)

    @property
    def errors(self):
        return [i for i in self.issues if i.level == "error"]

    @property
    def warns(self):
        return [i for i in self.issues if i.level == "warn"]

    def __len__(self):
        return len(self.issues)

    def report(self, max_lines=40):
        """人看的报告文本。"""
        if not self.issues:
            return "没有发现问题。"
        out = []
        if self.path:
            out.append("文件: %s" % self.path)
        for i in self.issues[:max_lines]:
            tag = "错误" if i.level == "error" else "提示"
            out.append(" %s  %s" % (tag, i))
        if len(self.issues) > max_lines:
            out.append(" ... 还有 %d 条没显示" % (len(self.issues) - max_lines))
        name = level_name(len(self.errors))
        if name:
            out.append("")
            out.append("共 %d 个错误 -> %s" % (len(self.errors), name))
        return "\n".join(out)


def format_exception(exc):
    """给开发版报错界面用的短回溯。"""
    lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    keep = []
    for ln in lines:
        if "site-packages" in ln:
            continue
        keep.append(ln.rstrip())
    return os.linesep.join(keep)
