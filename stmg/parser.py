# -*- coding: utf-8 -*-
"""STMG 剧本解析器 —— 把 .stm 剧本解析成语句树（AST）。

语法以 ciallo0721-cmd 的《Super Text Markdown Galgame language》设计稿为准。
设计稿里没写死、但解析必须拍板的地方，README 的「设计稿之外的补充约定」一节列了。
"""

import os
import re

from .errors import Issue, level_name  # noqa: F401  (level_name 供外部复用)

COMMENT_RE = re.compile(r"<--.*?-->", re.S)

# 设计稿通篇用的是全角引号，直接抄进 .stm 会解析失败，这里自动纠正。
QUOTE_FIX = {
    "\u201c": '"', "\u201d": '"',
    "\u2018": "'", "\u2019": "'",
}

# 这些词后面跟冒号时不是「标签」，是关键字
RESERVED = {"choose", "if", "else", "elif", "endif", "endchoose",
            "question", "set", "start"}

BLOCK_OPEN_RE = re.compile(r"^<(?P<name>[A-Za-z]*)$")
BLOCK_CLOSE_RE = re.compile(r"^</?(?P<name>[A-Za-z]*)>$")

CALL_RE = re.compile(r"^([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*\((.*)\)\s*$", re.S)
LABEL_RE = re.compile(r"^([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)\s*:\s*$")
IF_RE = re.compile(r"^If\s+(.+?)\s*:\s*$", re.I)
ELSE_RE = re.compile(r"^Else\s*:\s*$", re.I)
CHOOSE_RE = re.compile(r"^Choose\s*:\s*$", re.I)
QUESTION_RE = re.compile(r"^Question\s*:\s*(.*)$", re.I)
SET_RE = re.compile(r"^SET\s+([\w.]+)\s*=\s*(.*)$", re.I)
ASSIGN_RE = re.compile(r"^([A-Za-z_][\w.]*)\s*=\s*(.+)$", re.S)
SAY_RE = re.compile(r'^(?P<who>[^"\s][^"]*?)\s*[:：]?\s*(?P<text>".*")$', re.S)
BARE_SAY_RE = re.compile(r'^(".*")$', re.S)
HEADER_KV_RE = re.compile(r"^([A-Za-z_]\w*)\s*=\s*(.*)$")
# 一整行只由 "字符串" 和冒号组成 —— 这才是 Choose 的选项行
OPTIONS_RE = re.compile(r'^\s*(?:"[^"]*"\s*[:：]?\s*)+\s*$')

END_KEYWORDS = {"endif", "endchoose"}

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".avif")


def name_is_reserved(name):
    return name.lower() in RESERVED and name.lower() != "start"


class Script(object):
    """一份解析好的剧本。"""

    def __init__(self, path):
        self.path = path
        self.header = {}
        self.body = []
        self.ending = []
        self.issues = []

    @property
    def size(self):
        return self.header.get("size", (800, 600))

    @property
    def width(self):
        return self.size[0]

    @property
    def height(self):
        return self.size[1]

    @property
    def title(self):
        return self.header.get("title") or \
            os.path.splitext(os.path.basename(self.path))[0]

    @property
    def font(self):
        return self.header.get("font") or "Microsoft YaHei"

    def error_count(self):
        return len([i for i in self.issues if i.level == "error"])

    def walk(self, stmts=None):
        """按顺序遍历所有语句（含嵌套分支里的）。"""
        for s in (self.body if stmts is None else stmts):
            yield s
            if s["k"] == "if":
                for sub in self.walk(s["body"]):
                    yield sub
                for sub in self.walk(s.get("else_body") or []):
                    yield sub


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _norm_quotes(s):
    for a, b in QUOTE_FIX.items():
        s = s.replace(a, b)
    return s


def _split_blocks(text, issues):
    """按顶层的 < ... > 切块。返回 [(起始行号, [(行号, 原文), ...]), ...]"""
    blocks, cur = [], None
    for n, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if s == "<":
            if cur is not None:
                issues.append(Issue(cur[0], "上一个 < ... > 块没有闭合",
                                    "检查是不是漏了单独一行的 >"))
            cur = [n, []]
            continue
        if s in (">", "</>"):  # 单个 > 或者 </> 都当块结束
            if cur is None:
                issues.append(Issue(n, "多余的 > ：前面没有 < 开块"))
            else:
                blocks.append((cur[0], cur[1]))
                cur = None
            continue
        if cur is not None:
            cur[1].append((n, raw))
    if cur is not None:
        issues.append(Issue(cur[0], "整个剧本读完了，这个 < 块还没闭合"))
        blocks.append((cur[0], cur[1]))
    return blocks


def parse_args(s):
    """解析括号里的实参。容忍设计稿里漏掉的逗号（key="a"key="b"）。"""
    args, kwargs = [], {}
    i, n = 0, len(s)
    while i < n:
        if s[i] in " \t\r\n,":
            i += 1
            continue
        key = None
        m = re.match(r"([A-Za-z_]\w*)\s*=", s[i:])
        if m:
            key = m.group(1)
            i += m.end()
        if i < n and s[i] == '"':
            j, buf = i + 1, []
            while j < n:
                if s[j] == "\\" and j + 1 < n:
                    buf.append(s[j + 1])
                    j += 2
                    continue
                if s[j] == '"':
                    break
                buf.append(s[j])
                j += 1
            val = "".join(buf)
            i = j + 1
        else:
            m = re.match(r"[^,\s)]+", s[i:])
            if not m:
                i += 1
                continue
            val = m.group(0)
            i += m.end()
        if key:
            kwargs[key] = val
        else:
            args.append(val)
    return args, kwargs


def _indent_of(raw):
    return len(raw) - len(raw.lstrip(" \t"))


def _looks_like_image(v):
    v = (v or "").lower()
    return v.endswith(IMAGE_EXT) or "/" in v or "\\" in v


# --------------------------------------------------------------------------- #
# 语句解析
# --------------------------------------------------------------------------- #
def _parse_lines(lines, issues):
    """把 [(行号, 原文), ...] 解析成语句列表。缩进代表嵌套。"""
    items = []
    for n, raw in lines:
        if not raw.strip():
            continue
        items.append([n, _indent_of(raw), _norm_quotes(raw.strip())])

    pos = [0]

    def parse_block(indent, allow_empty=True, allow_end=True):
        stmts = []
        last_block = [False]      # 上一个语句是不是 If / Choose（决定 EndIf 归谁）
        while pos[0] < len(items):
            n, ind, s = items[pos[0]]
            if ind < indent:
                break
            if ind > indent:
                if allow_empty:
                    issues.append(Issue(n, "缩进比上一行深，但没有可归属的关键字",
                                        "If / Choose 的正文才需要缩进"))
                    pos[0] += 1
                    continue
                break

            low = s.lower().rstrip(":").strip()

            # --- 显式结束标记：只有真的在某个分支里才当结束，否则算多余的 ---
            if low in END_KEYWORDS:
                pos[0] += 1
                if last_block[0]:
                    # 紧接着前面那个 If / Choose，那就是给它收尾的，正常
                    last_block[0] = False
                    continue
                if allow_end:
                    break
                issues.append(Issue(n, "%s 是多余的：这一层没有 If / Choose 需要收尾"
                                    % s, "删掉它，或者检查缩进", "warn"))
                continue
            last_block[0] = False

            # --- Else: ---
            if ELSE_RE.match(s):
                pos[0] += 1
                stmts.append({"k": "else", "line": n})
                continue

            # --- Choose: ---
            if CHOOSE_RE.match(s):
                pos[0] += 1
                opts, decl_line = [], n
                while pos[0] < len(items):
                    on, oind, osx = items[pos[0]]
                    if oind > indent:
                        opts.extend(re.findall(r'"([^"]*)"', osx))
                        pos[0] += 1
                        continue
                    if oind == indent and OPTIONS_RE.match(osx):
                        opts.extend(re.findall(r'"([^"]*)"', osx))
                        pos[0] += 1
                        continue
                    break
                if not opts:
                    issues.append(Issue(decl_line, "Choose: 后面没有选项",
                                        '写成 "选项A":"选项B"'))
                stmts.append({"k": "choose", "options": opts, "line": decl_line})
                last_block[0] = True
                continue

            # --- If cond: ---
            m = IF_RE.match(s)
            if m:
                cond = m.group(1)
                pos[0] += 1
                if pos[0] < len(items) and items[pos[0]][1] > indent:
                    body = parse_block(items[pos[0]][1], allow_empty=False)
                else:
                    body = []
                    issues.append(Issue(n, "If 的正文既没缩进也没有 EndIf，分支范围只能靠推测",
                                        "给正文加 4 格缩进，或者写 EndIf"))
                    while pos[0] < len(items):
                        nn, nind, ns = items[pos[0]]
                        nlow = ns.lower().rstrip(":").strip()
                        if nind <= indent and (IF_RE.match(ns) or ELSE_RE.match(ns)
                                               or CHOOSE_RE.match(ns)
                                               or QUESTION_RE.match(ns)
                                               or LABEL_RE.match(ns)
                                               or nlow in END_KEYWORDS):
                            break
                        stay = pos[0]
                        body.extend(parse_block(nind, allow_empty=False))
                        if pos[0] == stay:
                            break
                else_body = []
                if pos[0] < len(items) and items[pos[0]][2].lower().startswith("else"):
                    pos[0] += 1
                    if pos[0] < len(items) and items[pos[0]][1] > indent:
                        else_body = parse_block(items[pos[0]][1], allow_empty=False)
                stmts.append({"k": "if", "cond": cond, "body": body,
                              "else_body": else_body, "line": n})
                last_block[0] = True
                continue

            # --- Question: ---
            m = QUESTION_RE.match(s)
            if m:
                pos[0] += 1
                prompt = m.group(1).strip()
                # 提示文字也可以写在 Question: 的下一行（缩进一个 "..."）
                if not prompt and pos[0] < len(items) and items[pos[0]][1] > indent:
                    on, _oi, osx = items[pos[0]]
                    if BARE_SAY_RE.match(osx):
                        prompt = osx
                        pos[0] += 1
                stmts.append({"k": "question", "prompt": prompt, "line": n})
                continue

            # --- SET name = value ---
            m = SET_RE.match(s)
            if m:
                pos[0] += 1
                stmts.append({"k": "set", "name": m.group(1),
                              "expr": m.group(2).strip(), "line": n})
                continue

            # --- 函数调用 S.play(...) / R.api(...) / STM.display(...) ---
            m = CALL_RE.match(s)
            if m:
                pos[0] += 1
                target, raw_args = m.group(1), m.group(2)
                args, kwargs = parse_args(raw_args)
                parts = target.split(".")
                obj = ".".join(parts[:-1]) if len(parts) > 1 else ""
                method = parts[-1]
                if obj.upper() == "S" and method.lower() == "character":
                    val = args[0] if args else ""
                    if _looks_like_image(val):
                        stmts.append({"k": "sprite", "path": val, "line": n})
                    else:
                        stmts.append({"k": "define", "name": val, "line": n})
                    continue
                stmts.append({"k": "call", "obj": obj, "method": method,
                              "args": args, "kwargs": kwargs, "line": n})
                continue

            # --- 赋值 name = value ---
            m = ASSIGN_RE.match(s)
            if m:
                pos[0] += 1
                stmts.append({"k": "set", "name": m.group(1),
                              "expr": m.group(2).strip(), "line": n})
                continue

            # --- Start: / 普通标签 ---
            m = LABEL_RE.match(s)
            if m and not name_is_reserved(m.group(1)):
                pos[0] += 1
                stmts.append({"k": "label", "name": m.group(1), "line": n})
                continue

            # --- 对白 ---
            m = SAY_RE.match(s)
            if m:
                pos[0] += 1
                stmts.append({"k": "say", "who": m.group("who").strip(),
                              "text": m.group("text"), "line": n})
                continue
            if BARE_SAY_RE.match(s):
                pos[0] += 1
                stmts.append({"k": "say", "who": None, "text": s, "line": n})
                continue

            issues.append(Issue(n, "看不懂这一行：%s" % s[:40],
                                "对照 README 的语法表"))
            pos[0] += 1
        return stmts

    return parse_block(0, allow_end=False)


def _parse_header(lines, issues):
    header = {}
    for n, raw in lines:
        s = _norm_quotes(raw.strip())
        if not s:
            continue
        m = HEADER_KV_RE.match(s)
        if not m:
            issues.append(Issue(n, "头部里有不是 key=value 的行：%s" % s[:30]))
            continue
        k, v = m.group(1), m.group(2).strip().strip('"')
        header[k.lower()] = v

    size = header.get("large") or header.get("size") or header.get("resolution") or "800x600"
    m = re.match(r"\s*(\d+)\s*[xX*\u00d7]\s*(\d+)", size)
    if m:
        header["size"] = (int(m.group(1)), int(m.group(2)))
    else:
        issues.append(Issue(None, "分辨率写得不认识：%s" % size, "应该像 800x600 这样"))
        header["size"] = (800, 600)

    header.setdefault("title", "")
    header.setdefault("font", "Microsoft YaHei")
    header.setdefault("ver", "1.0.0")
    header.setdefault("lang", "cn")
    return header


def parse_file(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        text = f.read()
    return parse_text(text, path)


def parse_text(text, path="<memory>"):
    sc = Script(path)
    if "\u201c" in text or "\u201d" in text:
        sc.issues.append(Issue(None, "剧本里用了全角引号 “ ”，已自动纠正为半角",
                               "建议以后直接用英文半角双引号", "warn"))
    text = COMMENT_RE.sub("", text)
    blocks = _split_blocks(text, sc.issues)
    if not blocks:
        sc.issues.append(Issue(None, "整个剧本里没有找到 < ... > 块"))
        return sc

    remaining = list(blocks)

    # 第一块：里面有 Start: 就当正文，否则当头
    first = remaining[0]
    joined = "\n".join(l for _, l in first[1])
    if re.search(r"^\s*Start\s*:", joined, re.M):
        sc.body = _parse_lines(first[1], sc.issues)
    else:
        sc.header = _parse_header(first[1], sc.issues)
        remaining.pop(0)

    if remaining:
        sc.body = _parse_lines(remaining[0][1], sc.issues)
        remaining.pop(0)
    if remaining:
        end_lines = []
        for _, ls in remaining:
            end_lines.extend(ls)
        sc.ending = _parse_lines(end_lines, sc.issues)

    if not sc.body:
        sc.issues.append(Issue(None, "正文是空的，游戏跑起来会直接结束"))

    _validate(sc)
    return sc


def _validate(sc):
    """静态检查。设计稿里点名「未定义角色就直接让角色说话」算错误。"""
    defined = set()
    labels = set()
    options = set()
    for s in sc.walk():
        if s["k"] == "define" and s["name"]:
            defined.add(s["name"])
        elif s["k"] == "label":
            labels.add(s["name"])
        elif s["k"] == "choose":
            options.update(s["options"])

    for s in sc.walk():
        if s["k"] == "say" and s["who"] and s["who"] not in defined:
            sc.issues.append(Issue(
                s["line"], "角色「%s」没有定义就直接说话了" % s["who"],
                '先在 Start: 下面写 S.character("%s")' % s["who"]))
        if s["k"] == "if":
            cond = s["cond"].strip()
            if cond.startswith('"') and cond.endswith('"') and len(cond) > 1:
                target = cond[1:-1]
                if options and target not in options:
                    sc.issues.append(Issue(
                        s["line"], "If 判断的选项「%s」不在任何 Choose 里" % target,
                        "检查选项文字有没有打错", "warn"))
        if s["k"] == "call" and s["obj"].upper() == "R" and s["method"] == "api":
            key = s["kwargs"].get("key", "")
            if key and key != "option" and not key.startswith("http") and len(key) < 12:
                sc.issues.append(Issue(
                    s["line"], "R.api 的 key 看起来太短，像是随手填的",
                    '正式项目请写 key=option，把密钥放到 options.stm', "warn"))
    if labels and "Start" not in labels:
        sc.issues.append(Issue(None, "正文里没有 Start:", "游戏会直接从第一句开始跑", "warn"))
