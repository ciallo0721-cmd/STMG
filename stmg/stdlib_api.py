# -*- coding: utf-8 -*-
"""STMG 暴露给剧本的内建能力：STM.python 白名单 + R.api 联网。

安全立场（README 里也会写）：
  * STM.python 只能加载白名单里的标准库，而且**只有开发模式能用**。
  * R.api 默认 5 秒超时，失败返回空串，绝不让网络问题卡死剧情。
"""

import importlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request

# 允许 STM.python 加载的库 —— 都是纯计算/玩具类，不碰文件系统和进程
PYTHON_WHITELIST = {
    "math", "random", "time", "datetime", "json", "re", "itertools",
    "functools", "collections", "statistics", "fractions", "decimal",
    "textwrap", "string", "unicodedata", "colorsys", "turtle", "webbrowser",
}

# 发布版里连这些也不给
RELEASE_BLOCKED = {"turtle", "webbrowser"}

# 「不需要库」的写法：stmg.python("none")
NO_LIB = {"none", "no", "null", "无", "没有", "不需要", "-"}

# python 代码块额外给的内建函数：只管计算和打印，不碰文件 / 进程 / 网络
PY_EXTRA_BUILTINS = (
    "print", "type", "isinstance", "tuple", "set", "frozenset",
    "any", "all", "map", "filter", "pow", "reversed", "chr", "ord",
    "divmod", "repr", "format", "getattr", "hasattr", "iter", "next",
    "slice", "bytes", "bytearray", "complex", "hex", "oct", "bin",
    "callable", "id", "hash", "dir",
)

API_TIMEOUT = 5


class ApiError(Exception):
    pass


def split_libraries(text):
    """把 "math,random" / "math、random" / "none" 拆成一串干净的库名。"""
    parts = re.split(r"[,，、;；\s]+", (text or "").strip())
    return [p for p in parts if p and p.lower() not in NO_LIB]


def check_library(name):
    """检查 STM.python / stmg.python 想加载的库能不能用。返回 (ok, 原因)。"""
    raw = (name or "").strip()
    if not raw:
        return False, "STM.python 没写库名（不需要库就写 none）"
    if raw.lower() in NO_LIB:
        # stmg.python("none")：明确表示「这个脚本不需要额外库」
        return True, ""
    for clean in split_libraries(raw):
        if not re.match(r"^[A-Za-z_]\w*$", clean):
            return False, "库名不合法：%s" % clean
        if clean not in PYTHON_WHITELIST:
            return False, "「%s」不在白名单里。允许的有：%s" % (
                clean, "、".join(sorted(PYTHON_WHITELIST)))
    return True, ""


def load_libraries(text):
    """按声明把白名单库 import 进来，返回 {名字: 模块}。加载不了就跳过。"""
    mods = {}
    for clean in split_libraries(text):
        if clean not in PYTHON_WHITELIST:
            continue
        try:
            mods[clean] = importlib.import_module(clean)
        except Exception:                            # noqa: BLE001
            pass
    return mods


def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    """python 代码块里的 import：只放白名单库进来，别的直接报错。"""
    root = (name or "").split(".")[0]
    if root not in PYTHON_WHITELIST:
        raise ImportError(
            "python 代码块只能 import 白名单里的库：%s（这里是 %s）"
            % ("、".join(sorted(PYTHON_WHITELIST)), name))
    return importlib.import_module(name)


def python_builtins():
    """python 代码块用的内建表：在 SAFE_BUILTINS 之上补 print / 受限 import。"""
    import builtins
    table = {n: getattr(builtins, n) for n in PY_EXTRA_BUILTINS}
    table["__import__"] = guarded_import
    return table


def call_api(url, key=None, method="GET", params=None, data=None):
    """R.api 的实现。返回 (ok, 结果文本)。"""
    if not url:
        return False, "R.api 没写 url"
    if not re.match(r"^https?://", url, re.I):
        url = "http://" + url

    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)

    headers = {"User-Agent": "STMG/1.0"}
    if key:
        headers["Authorization"] = "Bearer %s" % key

    body = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers,
                                 method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return False, "HTTP %s %s" % (e.code, e.reason)
    except urllib.error.URLError as e:
        return False, "连不上：%s" % e.reason
    except Exception as e:                      # noqa: BLE001 - 网络层什么都可能抛
        return False, "请求失败：%s" % e

    try:
        return True, json.loads(text)
    except ValueError:
        return True, text
