# -*- coding: utf-8 -*-
"""STMG 美化包（mod/）—— 只改外观，绝不碰引擎本体。

美化包就是一个个文件夹，放在 `mod/` 下面：

    mod/
    ├── active.json        当前启用哪个包（{"mod": "sakura"}）
    ├── none/              默认：引擎原生外观，什么都不改
    │   ├── mod.json       清单：名字 / 作者 / 版本 / 说明
    │   ├── gui.py         桌面端外观参数（**只能写 CONFIG = {...} 字面量**）
    │   ├── theme.css      网页版样式
    │   └── theme.js       网页版行为（受限沙箱里跑）
    └── sakura/            你自己做的美化包

外观参数的项和默认值全在 `uiconf.DEFAULTS` 里，改哪项写哪项即可。
优先级：引擎默认值 < 美化包 < 项目自己的 `custom/gui.py`（项目配置最大）。

════════════════════════════════════════════════════════════════════════
三条硬性限制（本模块会**静态检查**，不合格的包不能发布）
════════════════════════════════════════════════════════════════════════

1. 美化包里的 `.py` **只能声明字典，不能执行任何代码**。
   不写函数、不写 import、不写 open/eval/exec、不碰 `stmg` 模块。
   所以「用美化包改引擎行为」在物理上是不可能的——想改引擎就去改
   `stmg/` 里的源码，那才是引擎该改的地方。

2. 美化包不能包含引擎本体或任何可执行文件：
   没有 `stmg/`、`tools/`，没有 `.exe/.bat/.dll/.pyc`，没有 `start.py`。

3. 样式与脚本不能对外发请求、不能碰存档：
   CSS 禁 `@import` 和远程 `url()`；JS 禁 `localStorage` / `fetch` /
   `XMLHttpRequest` / `eval` / `Function` / `document.cookie` 等。

发布时产物一定叫「XXX_美化包」，不是 STMG 本体（见 tools/modpub.py）。
"""

import ast
import io
import json
import os
import re
import shutil
import tokenize

# --------------------------------------------------------------------------- #
# 目录与文件名约定
# --------------------------------------------------------------------------- #
MOD_DIRNAME = "mod"
MANIFEST_NAME = "mod.json"
ACTIVE_NAME = "active.json"
README_NAME = "README.md"
DEFAULT_ID = "none"
KIND = "beautify"                  # 清单里的 kind 固定是这个，标明「美化包」

FILES = {
    "gui": "gui.py",               # 桌面端外观（pygame）
    "css": "theme.css",            # 网页版样式
    "js": "theme.js",              # 网页版行为（沙箱）
}

# 引擎根：stmg/ 的上一级
ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 允许出现的后缀（纯数据 / 纯样式，都不可执行）
ALLOWED_EXT = {
    ".py", ".css", ".js", ".json", ".md", ".txt",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg", ".ico",
    ".ttf", ".otf", ".woff", ".woff2",
    ".mp3", ".wav", ".ogg", ".flac",
}

# 直接拒绝的后缀：可执行、可注入、编译产物
FORBIDDEN_EXT = {
    ".pyc", ".pyo", ".pyd", ".dll", ".exe", ".bat", ".cmd", ".ps1", ".psm1",
    ".sh", ".vbs", ".scr", ".msi", ".com", ".jar", ".lnk", ".so", ".dylib",
    ".zip", ".rar", ".7z", ".stmdec", ".pth", ".egg", ".whl", ".apk", ".dmg",
}

# 直接拒绝的文件名：引擎 / 工具链 / 打包器，一个都不许出现在美化包里
FORBIDDEN_NAMES = {
    "start.py", "start.bat", "launcher.py", "__init__.py", "__main__.py",
    "sitecustomize.py", "usercustomize.py", "conftest.py", "setup.py",
    "pyproject.toml", "requirements.txt", "stmg启动器.bat",
}

# 直接拒绝的目录名：放着引擎源码 / 打包产物 / 版本库的地方
FORBIDDEN_DIRS = {
    "stmg", "stmenc", "tools", "pyodide", "__pycache__", "dist", "projects",
    ".git", ".venv", "venv", ".idea", ".vscode", "site-packages",
}

LIMIT_TEXT = 256 * 1024            # 单个文本文件上限
LIMIT_ASSET = 4 * 1024 * 1024      # 单个素材上限
LIMIT_TOTAL = 16 * 1024 * 1024     # 整个美化包上限

TEXT_EXT = {".py", ".css", ".js", ".json", ".md", ".txt", ".svg"}

# `.py` 里出现这些字眼就拒绝（AST 检查之外的兜底防线）
PY_TOKEN_DENY = [
    r"\b__import__\b", r"\beval\s*\(", r"\bexec\s*\(", r"\bcompile\s*\(",
    r"\bopen\s*\(", r"\bglobals\s*\(", r"\blocals\s*\(", r"\bvars\s*\(",
    r"\bsetattr\s*\(", r"\bdelattr\s*\(", r"\bgetattr\s*\(",
    r"\bsubprocess\b", r"\bos\.\s*system", r"\bos\.\s*popen", r"\bpathlib\b",
    r"\bshutil\b", r"\bimportlib\b", r"\bctypes\b", r"\bmarshal\b", r"\bpickle\b",
    r"\bsocket\b", r"\brequests\b", r"\burllib\b",
    r"\bstmg\b", r"\bpygame\b", r"\bsys\b", r"\bbuiltins\b",
    r"__[A-Za-z_]+__",                 # 任何 dunder（__builtins__ 之类）
]

# 样式里不允许出现的东西
CSS_TOKEN_DENY = [
    (r"@\s*import", "@import 会把外部样式拉进来，美化包必须自带全部样式"),
    (r"expression\s*\(", "expression() 是老 IE 的脚本入口，禁止"),
    (r"javascript\s*:", "javascript: 伪协议禁止"),
    (r"-moz-binding", "-moz-binding 禁止"),
    (r"behavior\s*:", "behavior 禁止"),
    (r"url\s*\(\s*['\"]?\s*(https?:)?//", "url() 不能指向远程地址，本地素材请放进美化包"),
    (r"</\s*style", "不能出现 </style>（会污染宿主页面）"),
]

# 脚本里不允许出现的东西（第三项是正则 flags，省略就是 re.I）
JS_TOKEN_DENY = [
    (r"\beval\s*\(", "eval 禁止"),
    (r"\bnew\s+Function\b", "new Function 禁止"),
    (r"(?<![\w.$])Function\s*\(", "Function() 禁止", 0),
    (r"\bimport\s*\(", "动态 import 禁止"),
    (r"\brequire\s*\(", "require 禁止"),
    (r"\bdocument\s*\.\s*cookie\b", "不能读 cookie"),
    (r"\blocalStorage\b", "不能碰 localStorage（存档在里面）"),
    (r"\bsessionStorage\b", "不能碰 sessionStorage"),
    (r"\bindexedDB\b", "不能碰 indexedDB"),
    (r"\bfetch\s*\(", "不能发网络请求"),
    (r"\bXMLHttpRequest\b", "不能发网络请求"),
    (r"\bWebSocket\b", "不能开 WebSocket"),
    (r"\bsendBeacon\b", "不能发网络请求"),
    (r"\bwindow\s*\.\s*location\b", "不能改地址栏"),
    (r"\blocation\s*\.\s*(href|replace|assign)", "不能改地址栏"),
    (r"\bwindow\s*\.\s*(parent|top|opener)\b", "不能访问上层窗口"),
    (r"\bpostMessage\b", "postMessage 禁止"),
    (r"\bpyd(od)?ide\b", "不能碰 Pyodide 引擎内部"),
    (r"\b__STMG", "不能碰引擎内部变量"),
    (r"</\s*script", "不能出现 </script>（会污染宿主页面）"),
    (r"\bwriteSave\b|\breadSlot\b|\bclearSlot\b", "不能碰存档函数"),
]


# --------------------------------------------------------------------------- #
# 根目录与激活状态
# --------------------------------------------------------------------------- #
def roots(root=None):
    """候选根目录，按优先级：项目根 → 引擎根。"""
    out = []
    for p in (root, ENGINE_ROOT):
        if not p:
            continue
        p = os.path.abspath(p)
        if os.path.normcase(p) not in [os.path.normcase(q) for q in out]:
            out.append(p)
    return out


def mod_dir_of(root):
    return os.path.join(os.path.abspath(root), MOD_DIRNAME)


def find_dir(root=None):
    """返回第一个存在的 `mod/` 目录（没有就返回引擎根下面那个，方便创建）。"""
    for r in roots(root):
        d = mod_dir_of(r)
        if os.path.isdir(d):
            return d
    return mod_dir_of(ENGINE_ROOT)


def ensure(root=None):
    """确保 `mod/` 和默认的 `none/` 都在。返回 mod 目录。"""
    d = mod_dir_of(root or ENGINE_ROOT)
    os.makedirs(d, exist_ok=True)
    if not os.path.isdir(os.path.join(d, DEFAULT_ID)):
        create_mod(d, DEFAULT_ID, name="无美化", author="STMG",
                   desc="引擎原生外观，不做任何修改。", overwrite=False)
    return d


def read_active(root):
    """读某个根目录的 mod/active.json，返回 id 或 None（文件不存在）。"""
    p = os.path.join(mod_dir_of(root), ACTIVE_NAME)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (ValueError, OSError):
        return None
    mid = str(data.get("mod") or "").strip()
    return mid or None


def active_id(root=None):
    """当前启用的美化包 id：项目根写了就用项目的，否则用引擎根写的，都没有就是 none。"""
    for r in roots(root):
        mid = read_active(r)
        if mid:
            return mid
    return DEFAULT_ID


def set_active(mod_id, root=None):
    """把某个根目录设为启用 `mod_id`。root 省略时写引擎根（全局生效）。"""
    target = os.path.abspath(root or ENGINE_ROOT)
    d = mod_dir_of(target)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, ACTIVE_NAME)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"mod": mod_id or DEFAULT_ID}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return p


# --------------------------------------------------------------------------- #
# 发现与清单
# --------------------------------------------------------------------------- #
def manifest(path):
    """读一个美化包的 mod.json，返回字典（读不到就返回空字典）。"""
    p = os.path.join(path, MANIFEST_NAME)
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def list_mods(root=None):
    """列出所有能用的美化包，默认的 none 排最前，其余按名字排。"""
    seen, out = set(), []
    for r in roots(root):
        d = mod_dir_of(r)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.startswith(".") or name.startswith("_"):
                continue
            p = os.path.join(d, name)
            if not os.path.isdir(p) or os.path.normcase(name) in seen:
                continue
            seen.add(os.path.normcase(name))
            m = manifest(p)
            out.append({
                "id": name,
                "path": p,
                "root": r,
                "name": str(m.get("name") or name),
                "version": str(m.get("version") or "1.0.0"),
                "author": str(m.get("author") or "匿名"),
                "desc": str(m.get("desc") or ""),
                "kind": str(m.get("kind") or KIND),
                "default": name == DEFAULT_ID,
            })
    out.sort(key=lambda d: (not d["default"], d["id"]))
    return out


def find_mod(mod_id, root=None):
    """按 id 找到美化包目录，找不到返回 None。

    也可以直接给一个绝对 / 相对路径（比如项目内嵌了引擎、想用启动器那份
    美化包时，命令行会传绝对路径过来）。
    """
    if not mod_id:
        return None
    if os.path.isdir(mod_id) and os.path.isfile(os.path.join(mod_id, MANIFEST_NAME)):
        return os.path.abspath(mod_id)
    for r in roots(root):
        p = os.path.join(mod_dir_of(r), mod_id)
        if os.path.isdir(p):
            return p
    return None


# --------------------------------------------------------------------------- #
# 静态校验
# --------------------------------------------------------------------------- #
def _strip_comments(text, ext):
    if ext == ".css":
        return re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    if ext == ".js":
        text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
        return re.sub(r"(?m)^\s*//.*$", " ", text)
    return text


def _scan(text, rules, label, issues):
    for rule in rules:
        pat, why = rule[0], rule[1]
        flags = rule[2] if len(rule) > 2 else re.I
        m = re.search(pat, text, flags)
        if m:
            issues.append(("error", "%s 里出现禁止的写法 `%s`：%s" % (label, m.group(0)[:24], why)))


def _code_only(src):
    """只留下「真会执行的代码」——注释和字符串一律抹掉。

    这样文档里写「想改引擎请去 stmg/ 源码」就不会被误判成碰了 stmg 模块。
    """
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return src
    out = []
    for t in toks:
        if t.type == tokenize.COMMENT:
            continue
        if t.type == tokenize.STRING:
            out.append((t.type, '""'))
        else:
            out.append((t.type, t.string))
    try:
        return tokenize.untokenize(out)
    except (ValueError, IndexError):
        return src


_CONST_OK = (str, int, float, bool, type(None))


def _literal_ok(node, depth=0):
    """判断一个 AST 节点是不是纯字面量（没有函数调用、没有名字引用）。"""
    if depth > 6:
        return False
    if isinstance(node, ast.Constant):
        return isinstance(node.value, _CONST_OK)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return _literal_ok(node.operand, depth + 1)
    if isinstance(node, (ast.List, ast.Tuple)):
        return all(_literal_ok(e, depth + 1) for e in node.elts)
    if isinstance(node, ast.Dict):
        for k, v in zip(node.keys, node.values):
            if k is None or not _literal_ok(k, depth + 1) or not _literal_ok(v, depth + 1):
                return False
        return True
    return False


def _check_py(text, rel, issues):
    """`.py` 只允许：模块 docstring + 一个 `CONFIG = {字面量}`。"""
    try:
        tree = ast.parse(text, rel)
    except SyntaxError as e:
        issues.append(("error", "%s 第 %s 行语法错误：%s" % (rel, e.lineno, e.msg)))
        return

    for node in tree.body:
        if isinstance(node, ast.Expr):
            v = node.value
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                continue                                    # 模块文档字符串，随便写
            issues.append(("error", "%s 第 %d 行：只能写文档字符串和 CONFIG，"
                                    "不能有独立的表达式语句"
                            % (rel, getattr(node, "lineno", 0))))
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if names != ["CONFIG"]:
                issues.append(("error", "%s 第 %d 行：只允许给 CONFIG 赋值（发现 %s）"
                                % (rel, node.lineno,
                                   "、".join(getattr(t, "id", "?") for t in node.targets))))
                continue
            if not isinstance(node.value, ast.Dict):
                issues.append(("error", "%s 第 %d 行：CONFIG 必须是 {…} 字典字面量"
                                % (rel, node.lineno)))
            elif not _literal_ok(node.value):
                issues.append(("error",
                               "%s 第 %d 行：CONFIG 的值只能是字面量（数字 / 字符串 / "
                               "元组 / 列表 / 嵌套字典），不能写表达式、函数调用或变量名"
                               % (rel, node.lineno)))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            issues.append(("error", "%s 第 %d 行：美化包禁止 import（这就是「不许改引擎」那条规矩）"
                            % (rel, node.lineno)))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            issues.append(("error", "%s 第 %d 行：美化包禁止定义 %s（不能执行代码，只能声明外观）"
                            % (rel, node.lineno,
                               "函数" if not isinstance(node, ast.ClassDef) else "类")))
        else:
            issues.append(("error", "%s 第 %d 行：不允许的语句 %s（美化包只能声明 CONFIG）"
                            % (rel, getattr(node, "lineno", 0), type(node).__name__)))

    _scan(_code_only(text), [(p, "美化包的 .py 不许执行任何代码") for p in PY_TOKEN_DENY],
          rel, issues)


def verify(path, target=None):
    """校验一个美化包目录，返回 [(级别, 说明)]，级别是 "error" / "warn"。

    target 传 "engine" 时用引擎侧的标准（连 warn 也算问题），
    省略则只把 error 当硬性违规。
    """
    issues = []
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return [("error", "找不到美化包目录：%s" % path)]

    mid = os.path.basename(path)

    # ---------- 1. 结构 ----------
    man = manifest(path)
    if not os.path.isfile(os.path.join(path, MANIFEST_NAME)):
        issues.append(("error", "缺少 %s（清单文件，说明了包名 / 作者 / 版本）" % MANIFEST_NAME))
    elif not man:
        issues.append(("error", "%s 不是合法的 JSON 对象" % MANIFEST_NAME))
    else:
        kind = str(man.get("kind") or "").strip().lower()
        if kind and kind != KIND:
            issues.append(("error", "清单里的 kind 只能是 \"%s\"（美化包），"
                                    "现在写的是 \"%s\" —— 想改引擎本体请直接改 stmg/ 源码"
                            % (KIND, kind)))
        for k in ("name", "version", "author"):
            if not str(man.get(k) or "").strip():
                issues.append(("warn", "清单缺 %s 字段，发布时会用默认值" % k))

    # ---------- 2. 逐文件扫 ----------
    total = 0
    files = []
    for dirpath, dirnames, filenames in os.walk(path):
        for d in list(dirnames):
            low = d.lower()
            if low in FORBIDDEN_DIRS:
                issues.append(("error", "不允许出现 `%s/` 目录 —— 美化包不能带引擎本体、"
                                        "工具链或编译产物" % d))
                dirnames.remove(d)
            elif low in ("__pycache__", ".git"):
                dirnames.remove(d)
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, path).replace("\\", "/")
            files.append(rel)
            ext = os.path.splitext(fn)[1].lower()
            low = fn.lower()

            if low in FORBIDDEN_NAMES:
                issues.append(("error", "%s：这个文件名属于引擎 / 工具链，美化包里不许有" % rel))
                continue
            if ext in FORBIDDEN_EXT:
                issues.append(("error", "%s：%s 是可执行 / 编译产物，美化包一律不准带"
                                % (rel, ext)))
                continue
            if ext not in ALLOWED_EXT:
                issues.append(("error", "%s：不认识的后缀 %s（美化包只允许 .py/.css/.js/"
                                        "json/md 和图片音频字体）" % (rel, ext or "（无）")))
                continue

            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            total += size
            cap = LIMIT_TEXT if ext in TEXT_EXT else LIMIT_ASSET
            if size > cap:
                issues.append(("error", "%s：%s 太大了（%.1f MB，上限 %.1f MB）"
                                % (rel, ext, size / 1048576.0, cap / 1048576.0)))
                continue

            if ext not in TEXT_EXT:
                continue
            try:
                with open(full, "r", encoding="utf-8-sig", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue

            if ext == ".py":
                _check_py(text, rel, issues)
                if rel != FILES["gui"]:
                    issues.append(("error", "%s：美化包只允许一个 %s 文件，"
                                            "别的 Python 文件不许放"
                                    % (rel, FILES["gui"])))
            elif ext == ".html":
                issues.append(("error", "%s：美化包不许带 HTML（样式写 theme.css，"
                                        "行为写 theme.js）" % rel))
            elif ext == ".css":
                _scan(_strip_comments(text, ".css"), CSS_TOKEN_DENY, rel, issues)
            elif ext == ".js":
                body = _strip_comments(text, ".js")
                _scan(body, JS_TOKEN_DENY, rel, issues)
                if re.sub(r"\s|;", "", body) and "STMGTheme" not in text:
                    issues.append(("warn", "%s：脚本里没有出现 STMGTheme.register(...)，"
                                           "网页版不会调用它" % rel))

    if total > LIMIT_TOTAL:
        issues.append(("error", "美化包总体积 %.1f MB，超过 %.0f MB 上限"
                        % (total / 1048576.0, LIMIT_TOTAL / 1048576.0)))

    # ---------- 3. CONFIG 的项要对得上 ----------
    gui_path = os.path.join(path, FILES["gui"])
    if os.path.isfile(gui_path):
        cfg = None
        try:
            cfg = _read_config(gui_path)
        except Exception as e:                              # noqa: BLE001
            # 上面逐行检查已经报过的问题就不用再报一遍了
            if not any(lv == "error" and FILES["gui"] in msg for lv, msg in issues):
                issues.append(("error", "%s 读不出来：%s" % (FILES["gui"], e)))
        if isinstance(cfg, dict):
            from . import uiconf                             # 延迟导入，避免循环
            for k in cfg:
                if k not in uiconf.DEFAULTS:
                    issues.append(("warn", "%s 里的 \"%s\" 不是引擎认识的项，"
                                           "会被忽略（项和默认值见 stmg/uiconf.py）"
                                    % (FILES["gui"], k)))
    else:
        issues.append(("warn", "没有 %s，桌面端外观保持引擎默认" % FILES["gui"]))

    if not issues and target != "engine":
        issues.append(("ok", "没有问题"))
    return issues


def _read_config(gui_path):
    """从美化包的 gui.py 里取出 CONFIG 字典（先静态校验，再安全求值）。"""
    with open(gui_path, "r", encoding="utf-8-sig") as f:
        text = f.read()
    bad = []
    _check_py(text, os.path.basename(gui_path), bad)
    if any(lv == "error" for lv, _ in bad):
        raise ValueError("；".join(msg for lv, msg in bad if lv == "error")[:300])
    ns = {"__file__": gui_path, "__name__": "stmg_mod_gui"}
    exec(compile(text, gui_path, "exec"), ns)               # noqa: S102 - 已过静态校验
    cfg = ns.get("CONFIG")
    if cfg is None:
        return {}
    if not isinstance(cfg, dict):
        raise ValueError("CONFIG 不是字典")
    return cfg


def errors_of(issues):
    return [m for lv, m in issues if lv == "error"]


def warnings_of(issues):
    return [m for lv, m in issues if lv == "warn"]


# --------------------------------------------------------------------------- #
# 加载
# --------------------------------------------------------------------------- #
def load_theme(root=None, mod_id=None, disabled=False):
    """读取当前生效的美化包。

    返回一个字典：
        id / path / root / meta / config / css / js / issues / ok / reason
    `disabled=True`（命令行 --no-mod）时一律回退到 none。
    """
    out = {"id": DEFAULT_ID, "path": "", "root": "", "meta": {}, "config": {},
           "css": "", "js": "", "issues": [], "ok": True, "reason": ""}
    if disabled:
        out["reason"] = "命令行要求不使用美化包"
        return out

    if mod_id is None:
        mod_id = active_id(root)
    if not mod_id or mod_id == DEFAULT_ID:
        out["reason"] = "没有启用美化包"
        return out

    path = find_mod(mod_id, root)
    if not path:
        out["id"] = mod_id
        out["ok"] = False
        out["reason"] = "找不到美化包「%s」，已回退到原生外观" % mod_id
        return out

    out["id"] = os.path.basename(path)          # 允许直接传路径进来
    out["path"] = path
    out["root"] = os.path.dirname(os.path.dirname(path))
    out["meta"] = manifest(path)
    out["issues"] = verify(path, target="engine")
    errs = errors_of(out["issues"])
    if errs:
        out["ok"] = False
        out["reason"] = "美化包「%s」不合格，已回退到原生外观：%s" % (mod_id, errs[0])
        return out

    gp = os.path.join(path, FILES["gui"])
    if os.path.isfile(gp):
        try:
            out["config"] = _read_config(gp)
        except Exception as e:                              # noqa: BLE001
            out["ok"] = False
            out["reason"] = "美化包「%s」的 %s 读不出来：%s" % (mod_id, FILES["gui"], e)
            out["config"] = {}

    for key, fname in (("css", FILES["css"]), ("js", FILES["js"])):
        p = os.path.join(path, fname)
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8-sig") as f:
                    out[key] = f.read()
            except OSError:
                pass
    return out


# 这几个项是「路径」，项目里找不到时允许回退到美化包自己的目录
ASSET_KEYS = ("title_bg", "title_pic", "title_bgm", "type_se")


def _resolve_asset(value, theme, project_root):
    """美化包自带的图 / 音乐：项目里没有这个文件，就用美化包目录下的那一份。"""
    if not value or not isinstance(value, str) or not theme.get("path"):
        return value
    v = value.replace("\\", "/")
    if os.path.isabs(v) or v.startswith("stmgpack:") or "://" in v:
        return value
    if project_root and os.path.isfile(os.path.join(project_root, v)):
        return value
    local = os.path.join(theme["path"], v)
    if os.path.isfile(local):
        return local
    return value


def apply_to(config, theme, project_root=None):
    """把美化包的 CONFIG 合并进引擎的配置字典（原地改），返回改了几项。"""
    if not theme or not theme.get("config"):
        return 0
    n = 0
    for k, v in theme["config"].items():
        if v is None or k not in config:
            continue
        if k in ASSET_KEYS:
            v = _resolve_asset(v, theme, project_root)
        if isinstance(config.get(k), dict) and isinstance(v, dict):
            config[k].update(v)
        else:
            config[k] = v
        n += 1
    return n


# --------------------------------------------------------------------------- #
# 新建美化包
# --------------------------------------------------------------------------- #
def create_mod(root, mod_id, name=None, author=None, desc=None, overwrite=False):
    """在 `mod/` 里生成一个新的美化包骨架，返回目录路径。

    root 可以是 `mod/` 目录本身，也可以是它的上一个目录。
    """
    if os.path.basename(os.path.abspath(root)).lower() == MOD_DIRNAME:
        d = os.path.abspath(root)
    else:
        d = mod_dir_of(root)
    os.makedirs(d, exist_ok=True)

    # 文件夹名：中文可以用（引擎别的部分也支持中文名），但不能带路径分隔符
    mod_id = re.sub(r"[^0-9A-Za-z_.\-\u4e00-\u9fff]", "_", str(mod_id or "").strip())
    mod_id = mod_id.strip("._") or "my_theme"
    path = os.path.join(d, mod_id)
    if os.path.isdir(path) and not overwrite:
        if any(os.listdir(path)):
            raise OSError("美化包「%s」已经存在了" % mod_id)

    if mod_id == DEFAULT_ID:
        name = name or "无美化"
        author = author or "STMG"
        desc = desc or "引擎原生外观，不做任何修改。"

    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    os.makedirs(path, exist_ok=True)

    fields = {"id": mod_id, "name": name or mod_id,
              "author": author or "匿名",
              "desc": desc or "在这里写这个美化包做了什么。"}

    man = {
        "kind": KIND,
        "id": mod_id,
        "name": fields["name"],
        "version": "1.0.0",
        "author": fields["author"],
        "desc": fields["desc"],
        "engine": ">=1.0.0",
        "files": dict(FILES),
    }
    with open(os.path.join(path, MANIFEST_NAME), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
        f.write("\n")

    def _write(src_name, dst_name, fill=False):
        src = os.path.join(tpl, src_name)
        dst = os.path.join(path, dst_name)
        if not os.path.isfile(src):
            return
        with open(src, "r", encoding="utf-8-sig") as f:
            text = f.read()
        if fill:
            text = text.format(**fields)
        with open(dst, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    _write("mod_gui.py", FILES["gui"])
    _write("mod_theme.css", FILES["css"])
    _write("mod_theme.js", FILES["js"])
    _write("mod_README.md", README_NAME, True)
    return path


# --------------------------------------------------------------------------- #
# 给命令行用的小工具
# --------------------------------------------------------------------------- #
def brief(mod):
    tag = "（默认）" if mod.get("default") else ""
    return "%-18s %-12s v%-8s %s%s" % (mod["id"], mod["name"][:12],
                                      mod["version"], mod["author"], tag)


def summary(root=None):
    """一行行的状态文本，命令行和启动器都用它。"""
    aid = active_id(root)
    lines = ["美化包目录：%s" % find_dir(root), "当前启用：%s" % aid, ""]
    for m in list_mods(root):
        mark = "*" if m["id"] == aid else " "
        t = load_theme(root, m["id"])
        state = "正常" if t["ok"] else ("不合格" if t["path"] else "跳过")
        lines.append("%s %s  [%s]" % (mark, brief(m), state))
        if m["desc"] and m["id"] == aid:
            lines.append("    %s" % m["desc"])
    return "\n".join(lines)


def copy_mod(src, dst_root):
    """把一个美化包拷进某个 `mod/`（安装用）。返回目标路径。"""
    d = mod_dir_of(dst_root)
    os.makedirs(d, exist_ok=True)
    name = os.path.basename(os.path.abspath(src))
    dst = os.path.join(d, name)
    if os.path.isdir(dst):
        raise OSError("目标里已经有「%s」了" % name)
    shutil.copytree(src, dst)
    return dst
