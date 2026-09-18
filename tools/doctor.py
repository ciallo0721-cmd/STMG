#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""剧本健康度体检（T4 / #7）。

只读扫描一个 .stm 剧本（或一个含 script.stm 的项目目录），产出：
  · 台词统计（总句数 / 旁白 / 角色数 / 平均句长）
  · Choose 数量与分支数、If 最大嵌套深度
  · 孤儿 label（没人 S.jump 到、也不是 Start）
  · 素材清单（被引用数 / 未被任何 S.* 调用引用的文件）
  · 可疑项（变量被 If 判断却从未 SET、Choose 选项从未被 If 判断）
  · 0~100 健康度评分（算法写在本文件 score() 里）

用法：
    python tools/doctor.py demo
    python tools/doctor.py projects/my_story_2 --out 报告.md
    python tools/doctor.py demo/script.stm --json

铁律：本工具绝不修改任何剧本文件。
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from stmg import parser, options as optmod                 # noqa: E402
from stmg import project as proj                            # noqa: E402

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
AUD_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}

# 会被当作「素材调用」的 S.* 方法
ASSET_METHODS = {"cg", "bg", "background", "picture",
                 "character", "play", "sound", "voice"}

# S.character("角色1") 这种是「注册角色名」，不是文件；只有长得像路径的才算素材引用
_FILE_EXTS = IMG_EXTS | AUD_EXTS


def _looks_like_file(path):
    p = path.replace("\\", "/")
    if "/" in p or "\\" in p:
        return True
    return os.path.splitext(p)[1].lower() in _FILE_EXTS

# 跳过这些标识符（它们是关键字 / 命名空间 / 常见内置，不算「用户变量」）
_VAR_BLACKLIST = {
    "if", "else", "elif", "endif", "endchoose", "and", "or", "not", "in",
    "option", "true", "false", "none", "null", "stm", "r", "str", "int",
    "float", "bool", "len", "abs", "min", "max", "sum", "range", "round",
    "sorted", "print", "math", "os", "abs", "int", "float", "str",
}

# 匹配 S.方法( 这种调用起点
_CALL_RE = re.compile(
    r'\bS\.(cg|bg|background|picture|character|play|sound|voice)\s*\(', re.I)


def _match_paren(text, i):
    """从 i（指向 '('）开始，找到匹配的 ')' 位置。

    只数圆括号：STMG 的 {ruby:..} / [color:..] 是排版标记，不能当括号算。
    """
    depth = 0
    while i < len(text):
        c = text[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(text)


def scan_asset_refs(text):
    """扫一遍剧本文本，返回被引用的素材：(method, path, is_dynamic)。

    路径里若含 + ( ) STM. R. [ 等表达式拼接 -> 归为「动态路径」，不判缺失。
    """
    out = []
    for m in _CALL_RE.finditer(text):
        method = m.group(1).lower()
        j = _match_paren(text, m.end() - 1)
        args = text[m.end():j]
        sm = re.search(r'(["\'])(.*?)\1', args, re.S)
        if not sm:
            continue
        path = sm.group(2)
        if not path:
            continue
        # 角色名注册（无路径、无扩展名）不算素材文件引用
        if not _looks_like_file(path):
            continue
        is_dynamic = ('+' in args) or ('(' in args) or ('STM' in args) \
            or ('R.' in args) or ('[' in args)
        out.append((method, path, is_dynamic))
    return out


def _if_depth(stmts):
    """计算 If 的最大嵌套深度。"""
    d = 0
    for s in stmts:
        if s["k"] == "if":
            d = max(d, 1 + _if_depth(s.get("body", []) or []))
            d = max(d, 1 + _if_depth(s.get("else_body", []) or []))
    return d


def analyze(sc, game_dir, raw_text):
    """对一份解析好的剧本做健康度分析，返回报告字典。"""
    says = [s for s in sc.walk() if s["k"] == "say"]
    narr = [s for s in says if not s.get("who")]
    roles = sorted({s["who"] for s in says if s.get("who")})
    lengths = [len(s.get("text") or "") for s in says]
    avg_len = (sum(lengths) / len(lengths)) if lengths else 0

    chooses = [s for s in sc.walk() if s["k"] == "choose"]

    max_if_depth = _if_depth(sc.body)

    # 标签 / 跳转 / 孤儿 label
    label_names = {s["name"] for s in sc.walk() if s["k"] == "label"}
    jumps = set()
    for s in sc.walk():
        if s["k"] == "call" and s["obj"].upper() == "S" \
                and s["method"].lower() == "jump" and s.get("args"):
            jumps.add(s["args"][0])
    orphans = sorted(n for n in label_names
                    if n.lower() != "start" and n not in jumps)

    # 素材引用
    refs = scan_asset_refs(raw_text)
    referenced = set()       # 静态引用（正斜杠相对路径）
    missing = []             # (method, path) 静态引用但文件不存在
    dyn_count = 0
    for method, path, dyn in refs:
        if dyn:
            dyn_count += 1
            continue
        rel = path.replace("\\", "/")
        referenced.add(rel)
        if not os.path.isfile(os.path.join(game_dir, rel)):
            missing.append((method, rel))

    # 未引用素材：资产目录里、扩展名像素材、却没被任何 S.* 引用过的文件
    unref = []
    for cat in proj.ASSET_DIRS:
        base = os.path.join(game_dir, cat)
        if not os.path.isdir(base):
            continue
        for dirpath, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".") and not d.startswith("_")]
            for fn in files:
                if fn.startswith(".") or fn.startswith("_"):
                    continue
                ext = os.path.splitext(fn)[1].lower()
                if ext not in IMG_EXTS and ext not in AUD_EXTS:
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn), game_dir)
                rel = rel.replace("\\", "/")
                if rel not in referenced:
                    unref.append(rel)
    unref.sort()

    # 可疑项 1：变量被 If 判断却从未 SET
    sets = {s["name"] for s in sc.walk() if s["k"] == "set"}
    if_conds = [s["cond"] for s in sc.walk() if s["k"] == "if"]
    option_texts = set()
    for c in chooses:
        for o in c.get("options", []):
            option_texts.add(o)
    if_strings = set()       # If 里出现的字符串字面量（= 选项判断）
    var_refs = set()         # If 里出现的标识符（疑似变量）
    for cond in if_conds:
        for sm in re.finditer(r'"([^"]*)"', cond):
            if_strings.add(sm.group(1))
        # 先把字符串字面量抠掉，避免里面的中文被当成变量名
        stripped = re.sub(r'"[^"]*"', "", cond)
        for w in re.findall(r'[A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*', stripped):
            if w.lower() in _VAR_BLACKLIST:
                continue
            var_refs.add(w)
    uninit_vars = sorted(v for v in var_refs if v not in sets)

    # 可疑项 2：Choose 选项从未被 If 判断
    unjudged_opts = sorted(o for o in option_texts if o not in if_strings)

    errs = sc.error_count()

    score = score_health(errs, orphans, missing, uninit_vars, unjudged_opts)

    return {
        "title": sc.title,
        "path": sc.path,
        "say_total": len(says),
        "narration": len(narr),
        "roles": roles,
        "role_count": len(roles),
        "avg_say_len": round(avg_len, 1),
        "choose_count": len(chooses),
        "choose_branches": [len(c.get("options", [])) for c in chooses],
        "max_if_depth": max_if_depth,
        "label_count": len(label_names),
        "orphan_labels": orphans,
        "asset_referenced_count": len(referenced),
        "asset_missing_static": missing,
        "asset_dynamic_count": dyn_count,
        "asset_unreferenced": unref,
        "asset_unreferenced_count": len(unref),
        "suspicious_uninit_vars": uninit_vars,
        "suspicious_unjudged_options": unjudged_opts,
        "syntax_errors": errs,
        "score": score,
    }


def score_health(errs, orphans, missing, uninit_vars, unjudged_opts):
    """0~100 健康度评分。

    起始 100，按下列权重扣分（扣到 0 为止，不会变负）：
      · 语法错误：每项 -15
      · 孤儿 label：每个 -5
      · 缺失静态素材（被引用但文件不存在）：每个 -2（最多 -20）
      · 可疑项（变量未 SET / 选项未判断）：每个 -4（最多 -20）
    """
    susp = len(uninit_vars) + len(unjudged_opts)
    s = 100
    s -= errs * 15
    s -= len(orphans) * 5
    s -= min(len(missing), 10) * 2
    s -= min(susp, 8) * 4
    return max(0, min(100, s))


def _md(report):
    """把报告字典渲染成 Markdown 文本。"""
    r = report
    L = []
    L.append("# 剧本健康度报告")
    L.append("")
    L.append("- 剧本：`%s`" % r["path"])
    L.append("- 标题：**%s**" % (r["title"] or "(未命名)"))
    L.append("- 健康度评分：**%d / 100**" % r["score"])
    L.append("")
    L.append("## 台词统计")
    L.append("")
    L.append("- 台词总数：**%d** 句（旁白 %d 句）" % (r["say_total"], r["narration"]))
    L.append("- 角色数：**%d**（%s）" % (r["role_count"], "、".join(r["roles"]) or "—"))
    L.append("- 平均句长：**%.1f** 字符" % r["avg_say_len"])
    L.append("")
    L.append("## 结构")
    L.append("")
    L.append("- Choose 数量：**%d**" % r["choose_count"])
    if r["choose_branches"]:
        L.append("  - 各 Choose 分支数：%s" % "、".join(str(x) for x in r["choose_branches"]))
    L.append("- If 最大嵌套深度：**%d**" % r["max_if_depth"])
    L.append("- 标签数：**%d**" % r["label_count"])
    if r["orphan_labels"]:
        L.append("- ⚠ 孤儿 label（没人 S.jump 到）：%s" % "、".join(r["orphan_labels"]))
    else:
        L.append("- 孤儿 label：无")
    L.append("")
    L.append("## 素材")
    L.append("")
    L.append("- 被引用素材路径数：**%d**（其中动态拼接路径 %d 个，未断言缺失）"
             % (r["asset_referenced_count"], r["asset_dynamic_count"]))
    if r["asset_missing_static"]:
        L.append("- ⚠ 缺失静态素材（被引用但文件不存在）：%d 项" % len(r["asset_missing_static"]))
        for method, p in r["asset_missing_static"][:30]:
            L.append("  - `[%s] %s`" % (method, p))
        if len(r["asset_missing_static"]) > 30:
            L.append("  - … 还有 %d 项" % (len(r["asset_missing_static"]) - 30))
    else:
        L.append("- 缺失静态素材：无")
    L.append("- 未被引用的素材文件：**%d** 个" % r["asset_unreferenced_count"])
    for p in r["asset_unreferenced"][:30]:
        L.append("  - `%s`" % p)
    if len(r["asset_unreferenced"]) > 30:
        L.append("  - … 还有 %d 个" % (r["asset_unreferenced_count"] - 30))
    L.append("")
    L.append("## 可疑项")
    L.append("")
    if r["suspicious_uninit_vars"]:
        L.append("- ⚠ 被 If 判断却从未 SET 的变量：%s" % "、".join(r["suspicious_uninit_vars"]))
    else:
        L.append("- 变量未初始化：无")
    if r["suspicious_unjudged_options"]:
        L.append("- ⚠ 从未被 If 判断的 Choose 选项：%s"
                 % "、".join(r["suspicious_unjudged_options"]))
    else:
        L.append("- 选项未判断：无")
    if r["syntax_errors"]:
        L.append("")
        L.append("## 语法错误")
        L.append("")
        L.append("- 共 **%d** 个语法错误，详见 `python start.py --check 剧本`。" % r["syntax_errors"])
    L.append("")
    L.append("---")
    L.append("报告由 `tools/doctor.py` 生成（只读，不改剧本）。")
    return "\n".join(L)


def find_script(target):
    """target 是文件直接用；是目录就找 script.stm。返回绝对路径或空串。"""
    target = os.path.abspath(target)
    if os.path.isfile(target) and target.lower().endswith((".stm", ".stmdec")):
        return target
    for name in ("script.stm", "script.stmdec"):
        p = os.path.join(target, name)
        if os.path.isfile(p):
            return p
    return ""


def main(argv):
    args = argv[1:]
    as_json = "--json" in args
    args = [a for a in args if not a.startswith("--")]
    out_path = None
    if "--out" in args:
        i = args.index("--out")
        out_path = args[i + 1]
        args = args[:i] + args[i + 2:]

    target = args[0] if args else os.path.join(ROOT, "demo")

    path = find_script(target)
    if not path:
        print("没找到剧本：%s" % target)
        return 2

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            raw = f.read()
    except OSError as e:
        print("读不了剧本：%s" % e)
        return 2

    sc = parser.parse_file(path)
    game_dir = os.path.dirname(path)
    report = analyze(sc, game_dir, raw)

    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    md = _md(report)
    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(md + "\n")
            print("已写入报告：%s" % out_path)
        except OSError as e:
            print("写报告失败：%s" % e)
            return 2
    else:
        print(md)

    # 顺带提示 options 里有没有写加密口令（发布用）
    try:
        op = optmod.load_options(optmod.find_options(path))
        if not op.get("enc"):
            print("\n提醒：options.stm 还没写 Enc（加密口令），发布时会用不了。")
    except Exception:                      # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
