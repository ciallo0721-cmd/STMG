# -*- coding: utf-8 -*-
"""网页制作器（webmaker/）的后端工具：检查 / 素材扫描 / AST 导出。

制作器在浏览器里通过 Pyodide 调这里的函数，拿到的全是 JSON 字符串，
页面直接 JSON.parse。为什么另开一份而不复用 tools/check.py：那个是命令行
工具，打印的是给人看的中文报告；制作器要的是**带行号的结构化数据**，
用来在编辑器里画红点、在问题面板里点一下跳过去。语法判定仍然共用
stmg.parser —— 网页说没毛病、命令行说有毛病这种事不会发生。

对外四个函数：

    check(script_text, options_text, asset_paths)
        解析剧本，返回标题 / 分辨率 / 错误列表 / 统计 / 素材引用是否缺失
    ast(script_text)
        返回给页面内置解释器（--engine js）用的语句树
    options_meta(options_text)
        解析 options.stm，返回字段 + 它自己的 issue
    version()
        引擎版本号，制作器状态栏上显示用
"""

import json
import os
import re

from stmg import options as optmod
from stmg import parser
from stmg.errors import level_name

# 和 htmlpub.py 里的两份扩展名表保持一致：网页版认得的素材类型
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".avif"}
AUD_EXTS = {".ogg", ".mp3", ".wav", ".opus", ".m4a", ".flac", ".aac"}

# 会被当作「素材调用」的 S.* 方法（与 tools/doctor.py 的 ASSET_METHODS 同步）
ASSET_METHODS = ("cg", "bg", "background", "picture",
                 "character", "play", "sound", "voice")

_CALL_RE = re.compile(
    r'\bS\.(cg|bg|background|picture|character|play|sound|voice)\s*\(', re.I)

# 剧本里出现这些就算「动态路径」，静态判不了缺失，只提示不报错
_DYN_MARKS = ("+", "(", "STM", "R.", "[")


def _looks_like_file(path):
    """S.character("角色1") 里的「角色1」是注册名字，不是文件。

    判据和 doctor.py 一样：带路径分隔符就算文件；否则看扩展名。
    """
    p = path.replace("\\", "/")
    if "/" in p:
        return True
    return os.path.splitext(p)[1].lower() in (IMG_EXTS | AUD_EXTS)


def _match_paren(text, i):
    """从 i（指向左括号）找配对的右括号，只数圆括号。

    STMG 的 {ruby:..} / [color:..] 是排版标记，混进来会把配对算错。
    """
    depth = 0
    while i < len(text):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(text)


def scan_refs(text):
    """扫出剧本引用的素材：[(方法, 路径, 是否动态)]。

    这是 tools/doctor.py 里同一段逻辑的副本。复制而不是 import，是因为
    tools/ 不在网页版的模块清单里（那边只装 stmg/*.py），
    为了一个正则把整个 doctor.py 塞进 wasm 不划算。
    """
    out = []
    for m in _CALL_RE.finditer(text or ""):
        method = m.group(1).lower()
        j = _match_paren(text, m.end() - 1)
        args = text[m.end():j]
        sm = re.search(r'(["\'])(.*?)\1', args, re.S)
        if not sm:
            continue
        path = sm.group(2)
        if not path or not _looks_like_file(path):
            continue
        dynamic = any(k in args for k in _DYN_MARKS)
        out.append((method, path.replace("\\", "/"), dynamic))
    return out


def _count_nodes(node, acc):
    """递归数语句树：台词 / 选择 / 引擎调用 / python 块。"""
    if isinstance(node, dict):
        if "k" in node:
            k = node.get("k")
            acc["nodes"] += 1
            if k == "say":
                acc["say"] += 1
            elif k == "choose":
                acc["choose"] += 1
            elif k == "call":
                acc["call"] += 1
            elif k in ("py_block", "python"):
                acc["python"] += 1
        for v in node.values():
            _count_nodes(v, acc)
    elif isinstance(node, list):
        for v in node:
            _count_nodes(v, acc)


def _issue_dict(it):
    return {"line": int(getattr(it, "line", 0) or 0),
            "level": str(getattr(it, "level", "error") or "error"),
            "message": str(getattr(it, "message", "") or ""),
            "hint": str(getattr(it, "hint", "") or "")}


def check(script_text, options_text="", asset_paths="[]"):
    """解析剧本并返回制作器要的全部信息（一次调用塞满，省得反复过桥）。

    参数：
      script_text   剧本文本（script.stm 原文）
      options_text  options.stm 原文，可以空
      asset_paths   页面已知的素材相对路径，JSON 数组字符串；用来判缺失

    返回 JSON 字符串，键：
      ok / title / w / h / font / ver / lines
      issues        语法问题（带行号，error 和 warn 都在）
      errors        其中 error 的条数
      level         error 条数对应的级别叫法（A error / An error / Bro....）
      stats         台词 / 选择 / 调用 / python 块 / 语句总数
      refs          引用的素材：[{m,path,dynamic,found}]
      missing       被引用但页面里没有的静态素材
      unused        页面里有、但剧本没引用的素材
      options       options.stm 解析结果 + 它自己的 issues

    任何解析器抛异常都兜住返回 ok=false —— 制作器不能因为一份格式炸裂的
    剧本整个卡死，玩家还要继续改。
    """
    try:
        sc = parser.parse_text(script_text or "", "/game/script.stm")
    except BaseException as e:                              # noqa: BLE001
        return json.dumps({"ok": False, "fatal": "%s: %s" % (type(e).__name__, e),
                           "issues": [], "errors": 1, "level": "A error",
                           "title": "", "w": 1280, "h": 720, "font": "",
                           "ver": "", "lines": 0, "stats": {},
                           "refs": [], "missing": [], "unused": [],
                           "options": {}}, ensure_ascii=False)

    acc = {"say": 0, "choose": 0, "call": 0, "python": 0, "nodes": 0}
    try:
        _count_nodes(getattr(sc, "body", None), acc)
        _count_nodes(getattr(sc, "ending", None), acc)
    except BaseException:                                   # noqa: BLE001
        pass

    issues = [_issue_dict(i) for i in getattr(sc, "issues", [])]
    errors = len([i for i in issues if i["level"] == "error"])

    # ---- 素材 ----
    try:
        have = set(json.loads(asset_paths or "[]"))
    except BaseException:                                   # noqa: BLE001
        have = set()
    have = set(str(x).replace("\\", "/").lstrip("/") for x in have)

    refs, missing, seen = [], [], set()
    for method, path, dynamic in scan_refs(script_text):
        rel = path.lstrip("./").lstrip("/")
        found = rel in have
        refs.append({"m": method, "path": rel, "dynamic": bool(dynamic),
                     "found": bool(found)})
        if not dynamic:
            seen.add(rel)
            if not found and rel not in missing:
                missing.append(rel)

    unused = sorted(p for p in have
                    if p and p not in seen
                    and os.path.splitext(p)[1].lower() in (IMG_EXTS | AUD_EXTS))

    # ---- options.stm ----
    options, opt_issues = {}, []
    if options_text:
        try:
            options = optmod.parse_options_text(options_text)
            # parse_options_text 有可能把 issue 挂在返回的 dict 特殊键上，
            # 这里只取普通字段，顺便把非字符串的值转成字符串给页面显示
            options = {str(k): v for k, v in dict(options or {}).items()}
        except BaseException as e:                          # noqa: BLE001
            opt_issues.append({"line": 0, "level": "error",
                               "message": "options.stm 解析失败：%s" % e,
                               "hint": ""})
    if options_text and "Enc" not in options and "enc" not in options:
        opt_issues.append({"line": 0, "level": "warn",
                           "message": "options.stm 里没写 Enc，发布加密包时用不了",
                           "hint": '加上 Enc = "你的口令"'})

    return json.dumps({
        "ok": errors == 0,
        "title": str(getattr(sc, "title", "") or ""),
        "w": int(getattr(sc, "width", 1280) or 1280),
        "h": int(getattr(sc, "height", 720) or 720),
        "font": str(getattr(sc, "font", "") or ""),
        "ver": str(sc.header.get("ver", "") if hasattr(sc, "header") else ""),
        "lines": (script_text or "").count("\n") + 1,
        "issues": issues,
        "errors": errors,
        "level": level_name(errors) or "",
        "stats": acc,
        "refs": refs,
        "missing": missing,
        "unused": unused,
        "options": {"fields": options, "issues": opt_issues},
    }, ensure_ascii=False)


def ast(script_text):
    """返回 --engine js 用的语句树（导出单文件播放器时塞进 HTML）。

    解析失败返回 "null"，导出的播放器会退回 wasm 引擎，不会白屏。
    """
    try:
        sc = parser.parse_text(script_text or "", "/game/script.stm")
        data = {"title": sc.title,
                "ver": sc.header.get("ver", "1.0.0"),
                "w": sc.width, "h": sc.height,
                "body": sc.body, "ending": sc.ending}
        return json.dumps(data, ensure_ascii=False)
    except BaseException:                                   # noqa: BLE001
        return "null"


def options_meta(options_text):
    """单独解析 options.stm（制作器的设置面板用）。"""
    try:
        d = dict(optmod.parse_options_text(options_text or "") or {})
        return json.dumps({"ok": True, "fields": {str(k): v for k, v in d.items()}},
                          ensure_ascii=False)
    except BaseException as e:                              # noqa: BLE001
        return json.dumps({"ok": False, "why": str(e), "fields": {}},
                          ensure_ascii=False)


def version():
    """引擎版本（状态栏显示）。"""
    return json.dumps({"ok": True, "version": "maker-1.0",
                       "python": True}, ensure_ascii=False)
