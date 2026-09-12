# -*- coding: utf-8 -*-
"""STMG 暴露给剧本的内建能力：STM.python 白名单 + R.api 联网。

安全立场（README 里也会写）：
  * STM.python 只能加载白名单里的标准库，而且**只有开发模式能用**。
  * R.api 默认 5 秒超时，失败返回空串，绝不让网络问题卡死剧情。
"""

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

API_TIMEOUT = 5


class ApiError(Exception):
    pass


def check_library(name):
    """检查 STM.python 想加载的库能不能用。返回 (ok, 原因)。"""
    clean = (name or "").strip()
    if not clean:
        return False, "STM.python 没写库名"
    if not re.match(r"^[A-Za-z_]\w*$", clean):
        return False, "库名不合法：%s" % clean
    if clean not in PYTHON_WHITELIST:
        return False, "「%s」不在白名单里。允许的有：%s" % (
            clean, "、".join(sorted(PYTHON_WHITELIST)))
    return True, ""


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
