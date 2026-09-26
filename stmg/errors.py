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
    """按错误数量 n 返回设计稿定的「严重程度称呼」（见文件头）。

    这些阈值（1 / 40 / 50 / 100）是设计稿钦定的等级分界线，
    纯粹为了给用户一个「哎呀情况有多糟」的直观说法，不影响任何逻辑。
    0 个错误返回 None —— 调用方据此判断要不要显示这一行。
    """
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
        """把收集到的问题拼成一段人看的报告文本（尽量说人话，不堆术语）。

        max_lines 限制一次最多显示多少条，超出的用「还有 N 条没显示」带过，
        免得一个满是错的剧本把报告刷到没边。末尾若统计出错误数，会再补一句
        严重程度称呼（level_name）和一句「修掉带『错误』的就能正常启动」的引导。
        """
        if not self.issues:
            return "没有发现问题，剧本看起来没问题。"
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
            out.append("以上一共发现 %d 个错误（%s），修掉带「错误」的就能正常启动"
                       % (len(self.errors), name))
        return "\n".join(out)


def format_exception(exc):
    """给开发版报错界面用的「短回溯」——只保留和本项目有关的栈帧。

    正常报错会带出一长串 Python 标准库、pygame、第三方包的栈，对玩家来说
    全是噪声。这里把路径里含 "site-packages" 的帧（即第三方库内部）整段剔除，
    只留用户剧本 / 引擎源码这一层，开发版界面一眼就能定位到坏在哪一行。
    """
    lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    keep = []
    for ln in lines:
        if "site-packages" in ln:
            continue                    # 第三方库内部栈：开发界面不关心
        keep.append(ln.rstrip())
    return os.linesep.join(keep)
