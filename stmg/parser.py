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

# < ... python: 代码 ... > —— 内嵌的 Python 代码块。
# 它和顶层剧情块长得一模一样（都是 < ... >），所以要在 _split_blocks 之前
# 先整块抠出来，原地留一行占位符，等 _parse_lines 再还原成语句。
# 占位行必须**保持原有行数**（拿空行补齐），否则后面每一行的行号全会错位。
PY_BLOCK_OPEN_RE = re.compile(r"^<\s*(?:python|py)\s*:\s*(.*)$", re.I)
PY_BLOCK_KW_RE = re.compile(r"^(?:python|py)\s*:\s*(.*)$", re.I)
PY_BLOCK_MARK_RE = re.compile(r"^__STM_PYBLOCK_(\d+)__$")
PY_DELAY_RE = re.compile(r"^(?:delay\s*=\s*)?(\d+(?:\.\d+)?)\s*s?$", re.I)

PY_DELAY_DEFAULT = 3.0     # 代码块里 print 出来的行，默认每行隔 3 秒
PY_DELAY_MAX = 60.0

CALL_RE = re.compile(r"^([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*\((.*)\)\s*$", re.S)
# stm.os(...) —— 受控文件操作。外层只认 stm.os，内层再拆出 操作(path) 和可选的 ,"旧"to"新"
STM_OS_RE = re.compile(r"^\s*stm\.os\s*\((.*)\)\s*$", re.I | re.S)
STM_OS_INNER_RE = re.compile(
    r'^\s*([A-Za-z_]\w*)\s*\(\s*"([^"]*)"\s*\)'
    r'(?:\s*,\s*"([^"]*)"\s*to\s*"([^"]*)"\s*)?$',
    re.I | re.S)
LABEL_RE = re.compile(r"^([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)\s*:\s*$")
IF_RE = re.compile(r"^If\s+(.+?)\s*:\s*$", re.I)
ELSE_RE = re.compile(r"^Else\s*:\s*$", re.I)
CHOOSE_RE = re.compile(r"^Choose\s*:\s*$", re.I)
QUESTION_RE = re.compile(r"^Question\s*:\s*(.*)$", re.I)
SET_RE = re.compile(r"^SET\s+([\w.]+)\s*=\s*(.*)$", re.I)
ASSIGN_RE = re.compile(r"^([A-Za-z_][\w.]*)\s*=\s*(.+)$", re.S)
# 台词文本支持 "…" + 变量 这种拼接（运行时 _say_text 会 eval_expr 求值）。
# 所以文本部分用 ".* 吃掉到行尾（含 + 号），而不是钉死成单个引号串。
SAY_RE = re.compile(r'^(?P<who>[^"\s][^"]*?)\s*[:：]?\s*(?P<text>".*)$', re.S)
BARE_SAY_RE = re.compile(r'^(".*)$', re.S)
HEADER_KV_RE = re.compile(r"^([A-Za-z_]\w*)\s*=\s*(.*)$")
# 一整行只由 "字符串" 和冒号组成 —— 这才是 Choose 的选项行
OPTIONS_RE = re.compile(r'^\s*(?:"[^"]*"\s*[:：]?\s*)+\s*$')

# include 多文件剧本：解析期内联目标文件的正文
INCLUDE_RE = re.compile(r'^include\s+"([^"]*)"\s*$', re.I)
# 子程序调用：Call "标签" 或 Call 标签
CALLSUB_RE = re.compile(r'^Call\s+"([^"]*)"\s*$', re.I)
CALLSUB_RE2 = re.compile(r'^Call\s+([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)\s*$', re.I)
# 子程序返回
RETURN_RE = re.compile(r'^Return\s*$', re.I)
# 循环：Repeat N: / While 条件:（缩进子块）
REPEAT_RE = re.compile(r'^Repeat\s+(.+?)\s*:\s*$', re.I)
WHILE_RE = re.compile(r'^While\s+(.+?)\s*:\s*$', re.I)

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
        self.pyblocks = []      # 抠出来的 python 代码块，语句里按序号引用

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


def _dedent_code(code_lines):
    """去掉代码块整体的公共缩进（块写在 If 里面时，每行都会多 4 格）。"""
    body = list(code_lines)
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    pads = [len(ln) - len(ln.lstrip(" \t")) for ln in body if ln.strip()]
    cut = min(pads) if pads else 0
    return [ln[cut:] if len(ln) >= cut else ln.lstrip() for ln in body]


def _extract_pyblocks(text, issues):
    """把内嵌的 python 代码块抠出来，原地换成占位行。

    两种写法都认（缩进跟着外层，代码的共同缩进会被去掉）：

        <                <python:
        python:          print("1")
        print("1")       >
        >

    冒号后面可以只写一个数字，表示「每行 print 之间隔几秒」，默认 3。
    返回 (替换后的文本, [{"code": [...], "delay": 3.0, "line": 行号}, ...])
    """
    lines = text.splitlines()
    out, blocks = [], []
    i = 0
    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
        indent = raw[:len(raw) - len(raw.lstrip(" \t"))]
        head, spec, code_from = None, "", 0

        m = PY_BLOCK_OPEN_RE.match(s)          # <python: 3   （开口和关键词同一行）
        if m:
            head, spec, code_from = i, m.group(1), i + 1
        elif s == "<":                          # < 换行 然后  python:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                km = PY_BLOCK_KW_RE.match(lines[j].strip())
                if km:
                    head, spec, code_from = j, km.group(1), j + 1

        if head is None:
            out.append(raw)
            i += 1
            continue

        # 收集代码，直到单独一行的 >
        j, code = code_from, []
        while j < len(lines) and lines[j].strip() not in (">", "</>"):
            code.append(lines[j])
            j += 1
        if j >= len(lines):
            issues.append(Issue(head + 1, "python 代码块没有写 > 收尾",
                                "在代码最后单独写一行 >"))
            j = len(lines) - 1

        delay = PY_DELAY_DEFAULT
        txt = (spec or "").strip()
        if txt:
            dm = PY_DELAY_RE.match(txt)
            if dm:
                delay = max(0.0, min(PY_DELAY_MAX, float(dm.group(1))))
            else:
                issues.append(Issue(
                    head + 1, "python: 后面只认「隔几秒」，这里写的是：%s" % txt[:20],
                    "写成 python: 3 表示每行隔 3 秒；要跑代码请写在下面几行", "warn"))

        blocks.append({"code": _dedent_code(code), "delay": delay,
                       "line": head + 1, "code_line": code_from + 1})
        out.append(indent + "__STM_PYBLOCK_%d__" % (len(blocks) - 1))
        out.extend([""] * (j - i))              # 补齐行数，保证行号不错位
        i = j + 1
    return "\n".join(out), blocks


def _split_blocks(text, issues):
    """按顶层的 < ... > 切块。返回 [(起始行号, [(行号, 原文), ...]), ...]"""
    blocks, cur = [], None
    for n, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if s == "<":
            if cur is not None:
                issues.append(Issue(cur[0], "有一段剧情块（< ... >）还没写结尾的 >",
                                    "在它的最后单独写一行 > 收尾"))
            cur = [n, []]
            continue
        if s in (">", "</>"):  # 单个 > 或者 </> 都当块结束
            if cur is None:
                issues.append(Issue(n, "这里多了一个 >，但前面没有对应的 < 开头",
                                    "删掉这个 >，或在它前面补上 < 开块"))
            else:
                blocks.append((cur[0], cur[1]))
                cur = None
            continue
        if cur is not None:
            cur[1].append((n, raw))
    if cur is not None:
        issues.append(Issue(cur[0], "剧本读完了，但有一个 < 块一直没写 > 收尾",
                            "在文件末尾补一行 >"))
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


def _prefix_issue(iss, base):
    """给被 include 文件的报错加上文件名前缀，方便定位到 chapter1.stm:行12。"""
    if iss.line:
        msg = "%s:行%d %s" % (base, iss.line, iss.message)
    else:
        msg = "%s: %s" % (base, iss.message)
    return Issue(iss.line, msg, iss.hint, iss.level)


def _tag_file(stmts, base):
    """给 include 进来的语句打上原文件名（file 字段），递归进嵌套的 if/choose。

    这样运行时报错、调试都能知道这句来自哪个文件；顶层剧本的语句不带 file 字段
    （保持老行为）。
    """
    out = []
    for st in stmts:
        st = dict(st)
        st["file"] = base
        for key in ("body", "else_body"):
            if st.get(key):
                st[key] = _tag_file(st[key], base)
        out.append(st)
    return out


def _expand_include(raw, n, base_dir, incl_chain, issues):
    """处理 include "x.stm"：读目标文件、整体解析、把正文内联进来。

    返回 (语句列表, [Issue, ...])。找不到 / 循环 include 都通过 Issue 报错，
    **不崩溃**——主解析照常继续（缺文件的那段就当空）。
    """
    target = raw.strip().replace("\\", "/")
    if base_dir:
        target = os.path.join(base_dir, target)
    target = os.path.abspath(target)
    base = os.path.basename(target)

    if os.path.isfile(target):
        if target in incl_chain:
            # 循环 include（A include B、B 又 include A）：报错并停止展开
            return [], [Issue(n, "%s: 检测到循环 include（%s 已经被包含过了）"
                                 % (base, base),
                                 "检查是不是 A include B、B 又 include A 了")]
        try:
            with open(target, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except OSError as e:
            return [], [Issue(n, "%s: 读不了：%s" % (base, e))]
        # 嵌套 include 时把当前文件压进链，子文件里再 include 自己就报错
        sub_chain = list(incl_chain) + [target]
        sc2 = parse_text(text, target)
        # 被 include 的文件不需要 Start:（入口只在主剧本里），这条提醒对它没有意义，
        # 滤掉免得每 include 一个文件就多一条无用提示
        out_issues = [_prefix_issue(iss, base) for iss in sc2.issues
                      if "没有 Start" not in (getattr(iss, "message", "") or "")]
        return _tag_file(sc2.body, base), out_issues

    return [], [Issue(n, "%s: 文件找不到（include 解析不到「%s」）" % (base, raw),
                      "确认路径是相对当前剧本文件所在目录写的")]


# --------------------------------------------------------------------------- #
# 语句解析
# --------------------------------------------------------------------------- #
def _parse_lines(lines, issues, pyblocks=None, base_dir=None, incl_chain=None):
    """把 [(行号, 原文), ...] 解析成语句列表。缩进代表嵌套。

    base_dir / incl_chain 给 include 用：base_dir 是当前文件所在目录（相对它解析
    被包含文件），incl_chain 是已经展开过的文件绝对路径链（防循环）。
    """
    if incl_chain is None:
        incl_chain = []
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
                    issues.append(Issue(n, "这一行缩进太深，可它前面没有 If / Choose 之类的结构收它",
                                        "只有 If / Choose 里面的内容才需要缩进"))
                    pos[0] += 1
                    continue
                break

            low = s.lower().rstrip(":").strip()

            # --- python 代码块（_extract_pyblocks 留下的占位行）---
            pm = PY_BLOCK_MARK_RE.match(s)
            if pm:
                pos[0] += 1
                idx = int(pm.group(1))
                pb = pyblocks[idx] if pyblocks and idx < len(pyblocks) else {}
                stmts.append({"k": "pycode",
                              "code": list(pb.get("code") or []),
                              "delay": pb.get("delay", PY_DELAY_DEFAULT),
                              "code_line": pb.get("code_line") or (n + 1),
                              "line": pb.get("line") or n})
                last_block[0] = False
                continue

            # --- 显式结束标记：只有真的在某个分支里才当结束，否则算多余的 ---
            if low in END_KEYWORDS:
                pos[0] += 1
                if last_block[0]:
                    # 紧接着前面那个 If / Choose，那就是给它收尾的，正常
                    last_block[0] = False
                    continue
                if allow_end:
                    break
                issues.append(Issue(n, "这里的 %s 有点多余：当前这层没有需要它收尾的 If / Choose"
                                    % s, "如果不需要就删掉，或者检查缩进对不对", "warn"))
                continue
            last_block[0] = False

            # --- include 多文件剧本：解析期内联目标文件正文 ---
            im = INCLUDE_RE.match(s)
            if im:
                pos[0] += 1
                sub, sub_issues = _expand_include(im.group(1), n, base_dir,
                                                  incl_chain, issues)
                issues.extend(sub_issues)
                stmts.extend(sub)
                continue

            # --- 子程序返回 Return（栈空时由 run() 结束剧本）---
            if RETURN_RE.match(s):
                pos[0] += 1
                stmts.append({"k": "return", "line": n})
                continue

            # --- 子程序调用 Call "标签" / Call 标签 ---
            cm = CALLSUB_RE.match(s) or CALLSUB_RE2.match(s)
            if cm:
                pos[0] += 1
                stmts.append({"k": "call_sub", "name": cm.group(1), "line": n})
                continue

            # --- Repeat N: / While 条件: 循环（缩进子块）---
            rm = REPEAT_RE.match(s)
            if rm:
                pos[0] += 1
                if pos[0] < len(items) and items[pos[0]][1] > indent:
                    body = parse_block(items[pos[0]][1], allow_empty=False)
                else:
                    body = []
                    issues.append(Issue(n, "Repeat 下面的循环体没缩进，引擎不知道要循环到哪",
                                        "循环体往前缩进 4 格"))
                stmts.append({"k": "repeat", "count": rm.group(1).strip(),
                              "body": body, "line": n})
                continue

            wm = WHILE_RE.match(s)
            if wm:
                pos[0] += 1
                if pos[0] < len(items) and items[pos[0]][1] > indent:
                    body = parse_block(items[pos[0]][1], allow_empty=False)
                else:
                    body = []
                    issues.append(Issue(n, "While 下面的循环体没缩进，引擎不知道要循环到哪",
                                        "循环体往前缩进 4 格"))
                stmts.append({"k": "while", "cond": wm.group(1).strip(),
                              "body": body, "line": n})
                continue

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
                    issues.append(Issue(decl_line, "Choose: 下面没写任何选项",
                                        '在它下面写： "选项A" "选项B"'))
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
                    issues.append(Issue(n, "If 里面的内容既没缩进也没写 EndIf，引擎只能猜哪里结束",
                                        "正文往前缩进 4 格，或者显式写 EndIf 收尾"))
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

            # --- stm.os(...) —— 受控文件操作（DDLC 式彩蛋用）---
            m = STM_OS_RE.match(s)
            if m:
                inner = m.group(1)
                im = STM_OS_INNER_RE.match(inner)
                if not im:
                    issues.append(Issue(
                        n, "看不懂 stm.os 的写法：%s" % inner[:40],
                        '照着 STM.os(read("路径")) 或 STM.os(revision("路径"),"旧"to"新") 写'))
                    pos[0] += 1
                    continue
                op, fpath, find, replace = im.group(1), im.group(2), \
                    im.group(3), im.group(4)
                op = op.lower()
                if op not in ("read", "create", "remove", "revision"):
                    issues.append(Issue(
                        n, "stm.os 只支持 read / create / remove / revision，这里却是：%s" % op,
                        "把操作改成这四种之一"))
                    pos[0] += 1
                    continue
                if op == "revision" and find is None:
                    issues.append(Issue(
                        n, "revision 少写了要替换的内容",
                        '写全：stm.os(revision("x"),"旧"to"新")'))
                    pos[0] += 1
                    continue
                stmts.append({"k": "stm_os", "op": op, "path": fpath,
                              "find": find, "replace": replace, "line": n})
                pos[0] += 1
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
                        # 多张立绘可以同时在场，靠 tag 区分，pos 决定站哪
                        stmts.append({"k": "sprite", "path": val, "line": n,
                                      "args": args, "kwargs": kwargs})
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

            issues.append(Issue(n, "这一行没看懂：%s" % s[:40],
                                "对照 README 的语法说明检查一下写法"))
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
            issues.append(Issue(n, "剧本开头的设置里有一行不是「名称=值」：%s" % s[:30],
                                "头部每行写成 名称=值，例如 size=800x600"))
            continue
        k, v = m.group(1), m.group(2).strip().strip('"')
        header[k.lower()] = v

    size = header.get("large") or header.get("size") or header.get("resolution") or "800x600"
    m = re.match(r"\s*(\d+)\s*[xX*\u00d7]\s*(\d+)", size)
    if m:
        header["size"] = (int(m.group(1)), int(m.group(2)))
    else:
        issues.append(Issue(None, "分辨率看不懂：%s" % size, "写成例如 800x600 这种"))
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
    # include 相对「当前剧本文件所在目录」解析；<memory> 之类无路径的就相对当前目录
    base_dir = os.path.dirname(os.path.abspath(path)) if path else ""
    incl_chain = []
    if "\u201c" in text or "\u201d" in text:
        sc.issues.append(Issue(None, "剧本里用了中文引号 “ ”，已经帮你换成英文引号了",
                               "以后直接打英文半角引号更稳妥", "warn"))
    text = COMMENT_RE.sub("", text)
    # python 代码块也是 < ... > 包的，不先抠出来的话会被 _split_blocks 当成剧情块切开
    text, sc.pyblocks = _extract_pyblocks(text, sc.issues)
    blocks = _split_blocks(text, sc.issues)
    if not blocks:
        sc.issues.append(Issue(None, "剧本里没找到任何 < ... > 剧情块",
                               "用 < 和 > 把正文包起来"))
        return sc

    remaining = list(blocks)

    # 第一块到底是头还是正文？
    # 头部只认「名称=值」，所以：出现标签行或 python 代码块 -> 一定是正文；
    # 否则看「名称=值」占了多大比例，过半才算头部 —— 这样头部里写错一行仍会
    # 按头部报出「这行不是名称=值」，而整块剧情不会被误判成头。
    # （「Start」大小写不敏感，写成小写 start 也认）
    first = remaining[0]
    nonblank = [(n, l) for n, l in first[1] if l.strip()]
    joined = "\n".join(l for _, l in nonblank)
    kv = sum(1 for _, l in nonblank
             if HEADER_KV_RE.match(_norm_quotes(l.strip())))
    has_label = any(LABEL_RE.match(l.strip()) for _, l in nonblank)
    is_body = (has_label or PY_BLOCK_MARK_RE.search(joined)
               or (nonblank and kv * 2 < len(nonblank)))

    if is_body:
        sc.body = _parse_lines(first[1], sc.issues, sc.pyblocks, base_dir, incl_chain)
        remaining.pop(0)
    else:
        sc.header = _parse_header(first[1], sc.issues)
        remaining.pop(0)
        if remaining:
            sc.body = _parse_lines(remaining[0][1], sc.issues, sc.pyblocks,
                                   base_dir, incl_chain)
            remaining.pop(0)

    if remaining:
        end_lines = []
        for _, ls in remaining:
            end_lines.extend(ls)
        sc.ending = _parse_lines(end_lines, sc.issues, sc.pyblocks,
                                 base_dir, incl_chain)

    if not sc.body:
        sc.issues.append(Issue(None, "正文是空的，游戏一开场就结束了",
                               "在 Start: 下面写点剧情"))

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
                s["line"], "角色「%s」还没登场就开口说话了" % s["who"],
                '先在 Start: 下面用 S.character("%s") 介绍一下' % s["who"]))
        if s["k"] == "if":
            cond = s["cond"].strip()
            if cond.startswith('"') and cond.endswith('"') and len(cond) > 1:
                target = cond[1:-1]
                if options and target not in options:
                    sc.issues.append(Issue(
                        s["line"], "If 里判断的选项「%s」，在选项里没出现过" % target,
                        "确认 Choose 里的选项文字和这里完全一致", "warn"))
        if s["k"] == "pycode" and not s.get("code"):
            sc.issues.append(Issue(
                s["line"], "python 代码块里一行代码都没有",
                "在 python: 下面写代码，或者把这个块删掉", "warn"))
        if s["k"] == "call" and s["method"].lower() == "python" \
                and s["obj"].upper() in ("STM", "STMG"):
            from .stdlib_api import check_library
            ok, why = check_library(s["args"][0] if s["args"] else "")
            if not ok:
                sc.issues.append(Issue(
                    s["line"], "stmg.python 用不了：%s" % why,
                    '库名要写白名单里的；不需要库就写 stmg.python("none")'))
        if s["k"] == "call" and s["obj"].upper() == "R" and s["method"] == "api":
            key = s["kwargs"].get("key", "")
            if key and key != "option" and not key.startswith("http") and len(key) < 12:
                sc.issues.append(Issue(
                    s["line"], "R.api 的 key 好像是随便填的，太短了",
                    '正式发布请写 key=option，把密钥放进 options.stm', "warn"))
    if labels and not any(l.lower() == "start" for l in labels):
        sc.issues.append(Issue(None, "正文里没有 Start: 标记",
                               "没有也没关系，游戏会直接从头一句开始；想明确起点就加 Start:", "warn"))
