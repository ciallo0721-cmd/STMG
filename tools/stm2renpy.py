#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""STMG → Ren'Py 转换器（renpy2stm 的反向）。

    python tools/stm2renpy.py demo
    python tools/stm2renpy.py projects/我的游戏 --out dist/我的游戏_renpy
    python tools/stm2renpy.py projects/我的游戏 --no-assets     只转剧本，不拷素材
    python tools/stm2renpy.py projects/我的游戏 --title 游戏名

产物（默认 dist/<项目名>_renpy/）：

    game/
    ├── script.rpy        剧本正文，label start: 开始
    ├── stmg_config.rpy   标题 / 分辨率 / 角色定义 / 图像定义 / 兼容变量
    ├── images/           从 bg/ png/ gui/ 拷过来的图
    └── audio/            从 music/ 拷过来的音频
    转换报告.md            转换统计 + 需要手工处理的地方

把 `game/` 里的东西拷进 Ren'Py 工程（或者直接把整个 game/ 当工程皮肤），
再用 Ren'Py SDK 打开就能跑。

能转的：
    S.character("角色1")             ->  define 角色1 = Character("角色1")
    S.character("png/立绘.png", ...)  ->  image 立绘的 tag 定义 + show
    S.cg("bg/room.png")              ->  scene bg_room
    S.picture("png/note.png")        ->  show pic_note
    S.play / sound / voice / stop    ->  play music / sound / voice，stop music
    S.hide("x") / S.hide("sprite")   ->  hide x / 逐个 hide 在场立绘
    S.jump("x") / S.end()            ->  jump x / jump stmg_ending
    SET 变量 = 值                     ->  $ 变量 = 值
    Choose: + If "选项":             ->  menu + if "选项" in stmg_chosen
    Question:                        ->  $ stmg_answer = renpy.input(...)
    STM.display("文字")              ->  $ renpy.notify("文字")
    **粗体** [color=] [size=]        ->  {b} / {color=} / {size=}
    "前缀" + STM.ANSWER + "后缀"      ->  "前缀[stmg_answer]后缀"

转不了的（会进「转换报告.md」，不静默丢）：
    stm.os(...) 受控文件操作、R.api 联网（Ren'Py 里得自己用 renpy.fetch 写）、
    STM.python 扩展库、嵌套在分支里的 label

---------------------------------------------------------------------------
模块职责 / 定位
---------------------------------------------------------------------------
这是一个**命令行工具**，不是被别的模块 import 复用的库：

    * 被谁调用：用户在终端直接跑 `python tools/stm2renpy.py <项目>`，
      由本文件末尾的 `if __name__ == "__main__"` 进入 `main()`；
      反向工程 `renpy2stm.py` 是它的镜像兄弟（Ren'Py → STMG）。
    * 输入：STMG 项目目录（里面有 script.stm 剧本 + bg/ png/ music/ 素材）。
    * 输出：一份能直接塞进 Ren'Py SDK 跑的工程（`script.rpy` + `stmg_config.rpy`
      + 拷过来的 `images/` `audio/` + 一份 `转换报告.md`）。
    * 为什么需要它：STMG 自带的播放器用一套语法，Ren'Py 是另一套语法，
      这个脚本就是「语法翻译机」——尽量自动翻，翻不了的留痕迹让人手改。

设计上「能转的尽量转、转不了的明确标出来」：所有没成功转换的语句都会
写进 `todo` 列表，最后落进 `转换报告.md`，绝不明目张胆地丢内容。
"""

import os
import re
import shutil
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from stmg import parser                                  # noqa: E402
from stmg.markdown import TOKEN_RE, strip_quotes         # noqa: E402

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".avif")
AUDIO_EXT = (".ogg", ".mp3", ".wav", ".opus", ".m4a", ".flac")

# 项目里这些顶层目录名是「同类素材」，搬进 Ren'Py 工程时要把这一层吃掉，
# 否则会写出 audio/audio/xxx 这种看着像 bug 的路径。
AUDIO_TOP = ("audio", "music", "sound", "se", "voice", "bgm", "sfx")
IMAGE_TOP = ("images", "image", "img", "bg", "png", "pic", "picture",
             "cg", "sprite", "gui", "texture")


def relocate(rel, kind):
    """素材在 Ren'Py 工程里落到哪：图片统一进 images/，音频统一进 audio/。

    干什么：把 STMG 项目里的素材相对路径，重写成 Ren'Py 工程里的引用路径。
        核心规则是「吃掉顶层同名目录」——STMG 项目习惯用 bg/、music/ 这种
        顶层目录归类素材，但 Ren'Py 自己又有 images/、audio/ 一层，直接搬会
        变成 audio/audio/xxx 这种看着像 bug 的路径，所以这里把源头的 audio/
        music/ 等前缀去掉，再统一套上 images/ 或 audio/。

    参数：
        rel   素材相对项目根的路径，例如 "bg/room.png" 或 "music/bgm.ogg"。
        kind  "image" 或 "audio"，决定套哪一层前缀、以及吃哪个「同名顶层」表。

    返回：Ren'Py 工程内部的引用路径字符串（用 "/" 分隔），例如
        "images/room.png" / "audio/bgm.ogg"。

    删了会怎么样：所有图片/音频的落点计算都靠它（见 `_register`、`asset_ref`），
        删了素材就不知道该拷到哪、剧本里该引用什么名字，整个导出直接瘫痪。

    被谁调用：`_register()`（登记时算落点）、`asset_ref()`（引用时算落点）。
    """
    parts = [x for x in rel.replace("\\", "/").split("/") if x not in ("", ".")]
    top = IMAGE_TOP if kind == "image" else AUDIO_TOP
    if len(parts) > 1 and parts[0].lower() in top:
        parts = parts[1:]
    return "/".join((["images"] if kind == "image" else ["audio"]) + parts)


def kind_of(path):
    """看一个路径是图片还是音频（或者都不是）。

    干什么：根据文件扩展名判断素材类型，给 `relocate()` / `walk_assets()`
        决定「该套 images/ 还是 audio/ 前缀」「该不该当素材收集」。

    参数：path  任意文件路径或文件名（只看扩展名，路径本身无所谓）。

    返回：
        "image"  扩展名命中 IMAGE_EXT（png/jpg/...）；
        "audio"  扩展名命中 AUDIO_EXT（ogg/mp3/...）；
        ""       都不命中（比如 .txt/.stm 这种非素材文件）。

    删了会怎么样：素材分类全乱——图片可能被当音频、或者非素材文件被误拷，
        导出的工程引用路径全错。

    被谁调用：`walk_assets()`（决定要不要收集）、`relocate()`（决定套哪层前缀）、
        `asset_ref()`（决定原样放过还是当素材登记）。
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    return ""


def walk_assets(proj_dir):
    """项目里所有素材：(相对路径, 绝对路径)。

    干什么：遍历整个 STMG 项目目录，把所有「是图片或音频」的文件收集成
        (相对路径, 绝对路径) 的列表，排序后返回。会主动跳过那些不该碰的
        目录（隐藏目录、.venv、dist、game 等），避免把产物/环境再收集进来。

    参数：proj_dir  STMG 项目根目录的绝对路径。

    返回：[(rel, full), ...] 列表，rel 是相对 proj_dir 的 "/ " 分隔路径，
        full 是文件在磁盘上的绝对路径。已按 rel 排序，保证每次跑结果稳定。

    删了会怎么样：素材登记（`scan_assets`）没数据源，导出时图片/音频一个都
        拷不过去，剧本里所有 image/audio 引用全部悬空。

    被谁调用：`Conv.scan_assets()`（导出前先把项目素材全部登记一遍）。
    """
    out = []
    for dirpath, dirs, files in os.walk(proj_dir):
        dirs[:] = [d for d in dirs if not d.startswith((".", "_"))
                   and d not in (".venv", "dist", "game", "custom")]
        for fn in files:
            if kind_of(fn):
                full = os.path.join(dirpath, fn)
                out.append((os.path.relpath(full, proj_dir).replace("\\", "/"), full))
    out.sort()
    return out

# STM 的运行时命名空间 → Ren'Py 的 store 变量
STORE_MAP = {
    "STM.ANSWER": "stmg_answer",
    "STM.API": "stmg_api",
    "STM.OS": "stmg_os",
    "STM.NAME": "stmg_name",
    "STM.Q": "stmg_q",
    "R.RESULT": "stmg_api",
}

RESERVED = {
    "if", "else", "elif", "for", "while", "return", "def", "class", "import",
    "from", "as", "in", "is", "not", "and", "or", "pass", "none", "true",
    "false", "try", "except", "finally", "with", "lambda", "global",
    "nonlocal", "del", "assert", "raise", "yield", "break", "continue",
    "call", "jump", "menu", "show", "scene", "hide", "label", "play",
    "stop", "voice", "window", "nvl", "init", "python", "screen", "pause",
    "transform", "style", "image", "define", "default", "text", "at", "use",
    "on", "key", "bar", "grid", "side", "vbox", "hbox", "frame",
}

POS_OK = ("left", "center", "right", "truecenter", "topleft", "topright",
          "bottomleft", "bottomright", "offscreenleft", "offscreenright")


# --------------------------------------------------------------------------- #
# 文本工具
# --------------------------------------------------------------------------- #
def sanitize(name, fallback="x"):
    """把任意名字变成 Ren'Py 认的标识符（保留中文，其余换成下划线）。

    干什么：STMG 里角色名/label 名可能含空格、标点、中文，甚至以数字开头；
        Ren'Py 的标识符（image 名、变量名、label 名）可没这么随意，所以这里
        统一清洗：非法字符 → 下划线，头尾下划线去掉，数字/下划线开头的前面
        补一个前缀，撞到 Python/Ren'Py 保留字就加 "_v" 后缀避免冲突。

    参数：
        name     原始名字（可能很随便，如 "角色 1" / "123abc" / "if"）。
        fallback 清洗后万一变空字符串时用的兜底名（默认 "x"）。

    返回：一个干净、合法、Ren'Py 能用的标识符字符串。

    删了会怎么样：角色/立绘/背景/label 全都没法生成合法名字，导出文件里会
        冒出一堆语法错误的 image/define/label 行，Ren'Py 直接报错打不开。

    被谁调用：几乎被所有 `do_*` 语句处理函数用到（角色变量、image 名、
        label 名、变量名都要先过它）。
    """
    s = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", name or "").strip("_")
    if not s:
        s = fallback
    if s[0].isdigit() or s[0] == "_":
        s = "%s_%s" % (fallback, s)
    if s.lower() in RESERVED:
        s += "_v"
    return s


def esc_text(s):
    """Ren'Py 文本里的 [ { % 都是保留字符，纯文本部分得转义。

    干什么：Ren'Py 的字符串里 `[`、`{`、`%` 都有特殊含义（插值、text tag、
        格式符），如果剧本原文里就有这些字符、又不是想当语法用，就必须翻倍
        转义（`[`→`[[`、`{`→`{{`、`%`→`%%`），否则会被 Ren'Py 当成语法解析。

    参数：s  已经剥掉外层引号、待写入 Ren'Py 字符串的纯文本片段。

    返回：转义后的字符串（只在必要时翻倍，原文没有这三个字符就原样返回）。

    删了会怎么样：带 [ { % 的台词/旁白在 Ren'Py 里会解析失败或显示错乱，
        比如玩家名字里恰好有 [ 就会炸。

    被谁调用：`md2rpy()`（每个文本片段落盘前都先转义）、`say_text()`（拼接
        变量插值前后都对纯文本部分转义）。
    """
    s = s.replace("[", "[[").replace("{", "{{").replace("%", "%%")
    return s


def lit(s):
    """变成 Ren'Py 认得的一行字符串字面量。

    干什么：把任意 Python 字符串包成 Ren'Py 脚本里能直接写的一行双引号字面量。
        做了三件防错的事：反斜杠翻倍（避免被当转义）、双引号转义、把换行
        压成 `\n`（Ren'Py 一行字符串里不能有真换行）、顺手去掉回车。

    参数：s  原始文本（可能含引号、换行、反斜杠）。

    返回：形如 `"...."` 的字符串，可直接拼进 Ren'Py 的 say / menu / define 行。

    删了会怎么样：台词、选项、image 路径、notify 文本全都包不成合法字面量，
        要么引号没转义崩语法、要么多行文本直接把 .rpy 撑断行。

    被谁调用：几乎所有输出文本的地方（`md2rpy` 上游、`do_*` 里写台词/选项/
        路径/角色定义时），是文本落盘前最后一道包装。
    """
    out = (s.replace("\\", "\\\\").replace('"', '\\"')
            .replace("\r", "").replace("\n", "\\n"))
    return '"%s"' % out


def md2rpy(text):
    """STMG 的 md 内联标记 → Ren'Py 的 text tag。

    干什么：把 STMG 剧本里用的轻量 markdown 式内联标记，逐段翻译成 Ren'Py
        的 text tag。翻译映射（来自 stmg.markdown.TOKEN_RE 匹配到的语法元素）：
            **粗体**          → {b}...{/b}
            [color=xxx]文字   → {color=xxx}文字{/color}
            [size=n]文字      → {size=n}文字{/size}
            `代码`            → Ren'Py 没有等宽 tag，直接去掉反引号保留内容
            *斜体*            → {i}...{/i}
            ~~删除线~~        → {s}...{/s}
            ^上标^（rbase）   → 缩小 6 号字号模拟上标 (...){size=-6}(...){/size}
        纯文本部分要先过 `esc_text()` 转义，否则 [ { % 会被 Ren'Py 误读。

    参数：text  一条**已经剥掉外层引号**的台词/旁白/选项文本（可能含 md 标记）。

    返回：翻译好的 Ren'Py 文本字符串（含 {b} 等 tag），外层引号由 `lit()` 负责。

    删了会怎么样：所有 **粗体** / 颜色 / 字号 / 斜体 / 删除线 在导出后全部丢失，
        玩家看到的是一堆裸的 markdown 符号，格式全无。

    被谁调用：`say_text()`（台词翻译）、`do_question()`（输入提示翻译）、
        `do_choose()`（选项文字翻译），是富文本落盘的核心转换。

    注：TOKEN_RE 是正则（来自 stmg.markdown），它负责把一行文本切成「标记段 +
        纯文本段」，本函数只负责把每段标记翻译成对应 Ren'Py tag。
    """
    out, pos = [], 0
    for m in TOKEN_RE.finditer(text):
        if m.start() > pos:
            out.append(esc_text(text[pos:m.start()]))
        pos = m.end()
        if m.group("colortext") is not None:
            out.append("{color=%s}%s{/color}"
                       % (m.group("color"), esc_text(m.group("colortext"))))
        elif m.group("sizetext") is not None:
            out.append("{size=%s}%s{/size}"
                       % (m.group("size"), esc_text(m.group("sizetext"))))
        elif m.group("rbase") is not None:
            out.append("%s{size=-6}(%s){/size}"
                       % (esc_text(m.group("rbase")), esc_text(m.group("rtext"))))
        elif m.group("bold") is not None:
            out.append("{b}%s{/b}" % esc_text(m.group("bold")))
        elif m.group("strike") is not None:
            out.append("{s}%s{/s}" % esc_text(m.group("strike")))
        elif m.group("code") is not None:
            # Ren'Py 没有等宽 tag，去掉反引号保留内容
            out.append(esc_text(m.group("code")))
        elif m.group("italic") is not None:
            out.append("{i}%s{/i}" % esc_text(m.group("italic")))
    if pos < len(text):
        out.append(esc_text(text[pos:]))
    return "".join(out)


def split_concat(raw):
    """把 `"甲" + STM.ANSWER + "乙"` 拆成 ['"甲"', 'STM.ANSWER', '"乙"']。

    干什么：STMG 台词经常是「字符串字面量 + 变量 + 字符串字面量」拼起来的
        （比如 `"你好" + STM.ANSWER + "再见"`）。Ren'Py 里要变成
        "你好[stmg_answer]再见" 这种插值写法，所以这里先把整行按 `+` 切成段，
        并且**正确地处理引号**——只有不在字符串内部的 `+` 才算分隔符，字符串
        里带 `+` 不会被误切。

    参数：raw  原始台词表达式字符串（可能含有多个带引号的片段和 + 连接）。

    返回：去掉空白后的片段列表，每个元素要么是一段带引号的字符串字面量
        （如 `"甲"`），要么是一个变量/表达式（如 `STM.ANSWER`）。

    删了会怎么样：`say_text()` 没法拆分拼接台词，所有含变量插值的台词
        （输入回显、动态文本）都会整条无法转换。

    被谁调用：`say_text()`（处理含 + 拼接或 STM. 变量的台词时调用）。
    """
    parts, buf, in_str, esc, i = [], [], False, False, 0
    while i < len(raw):
        c = raw[i]
        if in_str:
            buf.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
                buf.append(c)
            elif c == "+":
                parts.append("".join(buf).strip())
                buf = []
            else:
                buf.append(c)
        i += 1
    parts.append("".join(buf).strip())
    return [p for p in parts if p]


def is_str_literal(s):
    """判断一个片段是不是「干净的字符串字面量」（两端双引号、内部无引号）。

    干什么：很多地方要区分「这一段是写死的字符串」还是「变量/表达式」。
        只有判定为干净字面量，才能放心地剥掉引号取内容；否则当表达式处理。

    参数：s  任意片段字符串（通常来自 `split_concat` 切出来的某一段）。

    返回：True / False。

    删了会怎么样：`say_text` / `do_if` / `do_question` 等都靠它分辨字面量和
        变量，删了拼接/条件/输入相关的逻辑会全部误判、崩掉。

    被谁调用：`say_text()`、`do_if()`、`do_question()`、`map_store()` 上游判断。
    """
    s = s.strip()
    return len(s) >= 2 and s[0] == '"' and s[-1] == '"' and '"' not in s[1:-1]


def map_store(expr):
    """STM.ANSWER / R.RESULT 之类的运行时名字 → Ren'Py 变量。

    干什么：STMG 剧本里用 `STM.ANSWER`、`STM.API`、`R.RESULT` 这类「运行时
        命名空间」变量；Ren'Py 没有这套东西，所以这里按 STORE_MAP 把它们逐个
        替换成对应的 Ren'Py store 变量（如 stmg_answer）。正则用 `\b...\b`
        包住关键字，保证只替换完整单词、不误伤包含这些子串的普通标识符。

    参数：expr  一个表达式字符串（可能是赋值右侧、条件、变量名等）。

    返回：替换后的表达式字符串（STM.* / R.* 已被换成 stmg_* 变量）。

    删了会怎么样：所有引用 STM.ANSWER / R.RESULT 等的赋值、条件、插值全部
        原样保留成 Ren'Py 不认识的 `STM.xxx`，导出后在 Ren'Py 里 NameError。

    被谁调用：`say_text()`（变量插值前先换名字）、`do_set()`（赋值右侧）、
        `do_if()`（条件表达式）。
    """
    out = expr
    for k, v in STORE_MAP.items():
        out = re.sub(r"\b%s\b" % re.escape(k), v, out)
    out = re.sub(r"\bSTM\.OS\b", "stmg_os", out)
    # and / or / not → Ren'Py 的 Python 表达式也认，但 trivially 保持原样
    return out


# --------------------------------------------------------------------------- #
# 转换主体
# --------------------------------------------------------------------------- #
class Conv(object):
    """STMG 剧本 → Ren'Py 的翻译器主体（一次转换一个剧本）。

    干什么：持有一份解析好的 STMG 脚本（self.script），把文件里出现的
        角色、立绘、背景、贴图、素材、label 逐个登记成 Ren'Py 能用的
        名字/定义，再按语句类型分派给各 do_<k> 方法生成 .rpy 文本行。
        同时维护 todo（转不了的残留）和 stats（统计计数）两份账。

    主要属性（在 __init__ 里初始化）：
        assets      STMG 素材相对路径 → Ren'Py 工程引用路径的映射（去重）
        chars       STMG 角色显示名 → Ren'Py 变量名
        images      完整 image 定义行（tag variant / bg_ / pic_）
        tags_live   当前在场的立绘 tag（供 hide 用）
        todo        转不了的语句清单（行号/原因/原文）
        stats       各语句类型的计数（导进转换报告.md）

    典型用法：conv = Conv(script, name, proj_dir); conv.scan_assets();
        body = conv.run(); cfg = conv.config_lines()
    被谁调用：main()（每次转换建一个 Conv 跑到底）。
    """
    def __init__(self, script, name, proj_dir=None):
        self.script = script
        self.name = name
        self.proj_dir = proj_dir
        self.assets = {}         # 剧本里的相对路径 -> Ren'Py 工程里的路径
        self._taken = set()      # 已经占掉的目标路径（防止两个源文件撞车）
        self.chars = {}          # 显示名 -> 变量名
        self.char_order = []
        self.images = {}         # image 名字（含空格分隔的 tag/variant）-> 定义行
        self.spr_by_path = {}    # (tag, path) -> image 名
        self.bg_by_path = {}     # 背景路径 -> image 名（同一张图只定义一次）
        self.pic_by_path = {}    # 贴图路径 -> image 名
        self.variant_used = {}   # tag -> set(已用 variant)
        self.tags_live = []      # 当前在场的立绘 tag（保持顺序）
        self.pic_name = None     # 当前叠加的 picture 名
        self.bg_name = None
        self.labels = set()
        self.todo = []
        self.stats = Counter()
        self.tmp = 0
        self.last_q = None
        self.menu_n = 0
        self.warned_pos = set()

    # ---------------- 资源 ---------------- #
    def _register(self, rel):
        """给一个素材相对路径分配 Ren'Py 工程里的落点（同一个源永远同一个落点）。"""
        key = rel.replace("\\", "/").strip().lstrip("/")
        if key in self.assets:
            return self.assets[key]
        dst = relocate(key, kind_of(key) or "image")
        base, ext = os.path.splitext(dst)
        i = 2
        while dst.lower() in self._taken:
            dst = "%s_%d%s" % (base, i, ext)
            i += 1
        self._taken.add(dst.lower())
        self.assets[key] = dst
        return dst

    def scan_assets(self):
        """先把项目里所有素材登记一遍，这样拷贝和引用不会各算各的。"""
        if not self.proj_dir:
            return
        for rel, _full in walk_assets(self.proj_dir):
            self._register(rel)

    def asset_ref(self, path):
        """STMG 里的相对路径 → Ren'Py 工程里的引用路径。"""
        p = (path or "").replace("\\", "/").strip().lstrip("/")
        if not p:
            return ""
        if not kind_of(p):
            return p                              # 不是图片/音频，原样放着
        return self.assets.get(p) or self._register(p)

    def _uniq(self, pool, name):
        """生成一个不跟 pool 里已有名字撞车的唯一名字（简单去重）。

        干什么：在登记 image / 角色 / 立绘 variant 时，如果算出来的名字
            已经有人用了，就在后面加 _2 / _3 ... 直到不重复为止，防止
            Ren'Py 里两个 image 同名导致后者覆盖前者。
        参数：
            pool  已占用名字的集合（self.images / self.variant_used[tag] 等），
                  key 就是名字本身。
            name  想要的名字（可能已经被占用）。
        返回：不冲突的名字（原样或带数字后缀）。
        删了会怎么样：同名 image / 立绘 variant 会互相覆盖，导出的 .rpy 里
            出现重复 image 定义，Ren'Py 警告甚至用错图。
        被谁调用：`bg_image()` / `pic_image()` / `sprite_name()`（生成时去重）。
        """
        if name not in pool:
            return name
        i = 2
        while "%s_%d" % (name, i) in pool:
            i += 1
        return "%s_%d" % (name, i)

    def sprite_name(self, tag, path):
        """立绘 image 名 = 「tag variant」，同 tag 会互相替换（和 STMG 一致）。

        tag 和文件名撞了（比如 tag=aming_normal、文件也叫 aming_normal.png）就只留一个词，
        省得写出 `show aming_normal aming_normal` 这种。
        """
        key = (tag, path)
        if key in self.spr_by_path:
            return self.spr_by_path[key]
        tag_s = sanitize(tag, "sprite")
        stem = os.path.splitext(os.path.basename(path.replace("\\", "/")))[0]
        variant = sanitize(stem, "v")
        used = self.variant_used.setdefault(tag_s, set())
        if variant != tag_s:
            variant = self._uniq(used, variant)
            used.add(variant)
        full = tag_s if variant == tag_s else "%s %s" % (tag_s, variant)
        self.images[full] = 'image %s = %s' % (
            full, lit(self.asset_ref(path)))
        self.spr_by_path[key] = full
        return full

    def bg_image(self, path):
        """背景路径 → image 名（bg_xxx），同一张路径只定义一次。

        干什么：把 STMG 的 S.cg / S.bg 背景路径，登记成一个 Ren'Py image 定义
            （如 image bg_room = "images/room.png"），并缓存到 bg_by_path，
            保证同一张背景在剧本里多处出现也只输出一条 image 定义。
            名字规则：文件名 stem 若已以 bg 开头就直接用，否则加 bg_ 前缀。
        参数：path  背景素材的（项目内）相对路径或带前缀路径。
        返回：Ren'Py 的 image 名（如 "bg_room"）。
        删了会怎么样：`do_call` 里 bg/cg 分支没法生成 image 定义和 scene，
            所有换背景语句都转不出来。
        被谁调用：`do_call()`（S.cg / S.bg / S.background 分支）。
        """
        if path in self.bg_by_path:
            return self.bg_by_path[path]
        stem = os.path.splitext(os.path.basename(path.replace("\\", "/")))[0]
        base = sanitize(stem, "bg")
        nm = base if base.lower().startswith("bg") else "bg_" + base
        nm = self._uniq(self.images, nm)
        self.images[nm] = 'image %s = %s' % (nm, lit(self.asset_ref(path)))
        self.bg_by_path[path] = nm
        return nm

    def pic_image(self, path):
        """贴图路径 → image 名（pic_xxx），同一张只定义一次（和 bg_image 对称）。

        干什么：与 `bg_image()` 对称，处理 S.picture 叠加图：登记成
            image pic_xxx = "images/xxx.png"，名字规则是文件名 stem 不以 pic
            开头就加 pic_ 前缀，同样缓存到 pic_by_path 去重。
        参数：path  贴图素材的相对路径。
        返回：Ren'Py 的 image 名（如 "pic_note"）。
        删了会怎么样：`do_picture()` 没法生成 image 定义和 show，叠加图转不出来。
        被谁调用：`do_picture()`。
        """
        if path in self.pic_by_path:
            return self.pic_by_path[path]
        stem = os.path.splitext(os.path.basename(path.replace("\\", "/")))[0]
        base = sanitize(stem, "pic")
        nm = base if base.lower().startswith("pic") else "pic_" + base
        nm = self._uniq(self.images, nm)
        self.images[nm] = 'image %s = %s' % (nm, lit(self.asset_ref(path)))
        self.pic_by_path[path] = nm
        return nm

    def char_var(self, disp):
        """显示名 → Ren'Py 角色变量名（"角色1" → 角色1），缓存并记顺序。

        干什么：把 STMG 的角色「显示名」映射成一个 Ren'Py 角色变量名。
            同名直接返回缓存；新名字先过 `sanitize()` 清洗成合法标识符，
            若和已有角色变量撞了就加数字后缀；同时记入 char_order 保持
            角色定义输出的稳定顺序。
        参数：disp  STMG 里的角色显示名（可能含中文/空格，如 "角色 1"）。
        返回：Ren'Py 角色变量名（如 "角色1"），可直接用于 define X = Character(...)。
        删了会怎么样：所有 `do_say()` 的「谁在说话」、以及 config 里的角色定义
            都生成不了，台词变成没有角色的裸文本。
        被谁调用：`do_say()`（拼台词主语）、`do_define()`（登记角色声明）。
        """
        if disp in self.chars:
            return self.chars[disp]
        var = sanitize(disp, "char")
        i = 2
        while var in (self.chars.values()):
            var = "%s_%d" % (sanitize(disp, "char"), i)
            i += 1
        self.chars[disp] = var
        self.char_order.append(disp)
        return var

    # ---------------- 文本 ---------------- #
    def say_text(self, raw, line, depth):
        """台词原文 → (要预先插入的 $ 行, Ren'Py 字符串字面量)。

        md 标记可能跨越拼接（`"[color=x]**" + STM.ANSWER + "**[/color]"`），
        所以先把变量换成哨兵，整条拼好再统一做 md 转换，最后才把哨兵换成插值。
        """
        raw = (raw or "").strip()
        pre = []
        if "+" not in raw and "STM." not in raw:
            text = raw[1:-1] if is_str_literal(raw) else strip_quotes(raw)
            return pre, lit(md2rpy(text))

        reps, parts = [], []                        # [(哨兵, Ren'Py 插值)]
        for c in split_concat(raw):
            if is_str_literal(c):
                parts.append(c[1:-1])
                continue
            expr = map_store(c)
            if re.match(r"^[A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*$", expr):
                val = "[%s]" % expr                 # 简单变量直接插值
            else:
                self.tmp += 1
                name = "stmg_tmp%d" % self.tmp
                pre.append("%s$ %s = %s" % ("    " * depth, name, expr))
                val = "[%s]" % name
            ph = "\x01%d\x01" % len(reps)
            reps.append((ph, val))
            parts.append(ph)

        rpy = md2rpy("".join(parts))
        for ph, val in reps:
            rpy = rpy.replace(ph, val)
        return pre, lit(rpy)

    # ---------------- 语句 ---------------- #
    def emit(self, stmts, depth, lines):
        """把一串 STMG 语句逐个翻译成 Ren'Py 行，追加到 lines 列表。

        干什么：翻译主循环——遍历语句列表，按语句类型 k 找对应的 do_<k>
            方法分派下去；遇到不认识的语句类型，记进 todo 并输出一行
            `# [没转] ...` 注释，绝不静默丢掉。depth 控制缩进层数。
        参数：
            stmts  语句字典列表（来自 script.walk() / 分支 body）。
            depth  当前缩进深度（Ren'Py 用 4 空格缩进表达层级）。
            lines  输出行列表（原地追加，不返回）。
        返回：无（结果在 lines 里）。
        删了会怎么样：整个「语句 → Ren'Py 行」的分派核心没了，所有剧本
            正文都没法翻译，run() 直接空转。
        被谁调用：`run()`（顶层 body / ending）、`do_if()`（条件分支 body）。
        """
        pad = "    " * depth
        for s in stmts:
            k = s["k"]
            fn = getattr(self, "do_" + k, None)
            if fn is None:
                self.todo.append((s.get("line"), "不认识的语句类型 %s" % k, ""))
                lines.append("%s# [没转] 不认识的语句 %s" % (pad, k))
                continue
            fn(s, depth, lines)

    # --- 台词 ---
    def do_say(self, s, depth, lines):
        """把一条 say 语句翻译成 Ren'Py 台词行（带角色名或旁白）。

        干什么：区分「旁白」（没有 who）和「角色台词」（有 who）。旁白直接
            写一行字符串；角色台词写成 `角色变量 "文本"`。两种情况都先过
            `say_text()` 处理拼接/变量插值/md 标记，并累加对应的统计计数。
        参数：
            s      say 语句字典，含 who（可选）/ text / line。
            depth  缩进深度。
            lines  输出行列表（原地追加）。
        返回：无。
        删了会怎么样：剧本里所有的对话/旁白都转不出来，导出后只剩选项和跳转。
        被谁调用：`emit()` 按 k=="say" 分派。
        """
        pad = "    " * depth
        if not s.get("who"):
            pre, text = self.say_text(s["text"], s["line"], depth)
            lines.extend(pre)
            lines.append("%s%s" % (pad, text))
            self.stats["旁白"] += 1
            return
        who = self.char_var(s["who"])
        pre, text = self.say_text(s["text"], s["line"], depth)
        lines.extend(pre)
        lines.append("%s%s %s" % (pad, who, text))
        self.stats["台词"] += 1

    # --- python 代码块 ---
    def do_pycode(self, s, depth, lines):
        """STMG 的 python 代码块：Ren'Py 里没有完全对应的自动写法，标成待办。

        干什么：STMG 允许剧本里嵌 `python:` 代码块，但 Ren'Py 的 python 块
            语义不完全一致，没法一键翻。这里不强行转换，只输出一行 `# [没转]`
            注释标明行数，并把「建议改成 python: 块或 $ 语句」记进 todo，
            留给人手工处理，绝不丢内容。
        参数：
            s      pycode 语句字典，含 code（行列表）/ line。
            depth  缩进深度。
            lines  输出行列表（原地追加注释）。
        返回：无。
        删了会怎么样：剧本里嵌的 python 逻辑在导出后完全消失且无痕，玩家
            跑 Ren'Py 版会发现逻辑缺一块，还不知道缺了啥。
        被谁调用：`emit()` 按 k=="pycode" 分派。
        """
        pad = "    " * depth
        self.todo.append((s.get("line"),
                          "python 代码块转不过去（Ren'Py 里没有对应写法）",
                          "搬到 Ren'Py 就手工改成 python: 块或 $ 语句"))
        lines.append("%s# [没转] python 代码块（%d 行）"
                     % (pad, len(s.get("code") or [])))

    # --- 角色注册 ---
    def do_define(self, s, depth, lines):
        """处理 S.character("名字")：登记一个角色变量（真正的定义在 config 里）。

        干什么：STMG 的 `S.character("名字")` 声明一个角色。这里不输出 .rpy
            行（角色 define 统一在 `config_lines()` 里按 char_order 输出），
            只调用 `char_var()` 把显示名登记/映射成变量名，并累加统计。
        参数：
            s      define 语句字典，含 name。
            depth  缩进深度（本函数不输出行，仅登记）。
            lines  输出行列表（本函数不追加）。
        返回：无。
        删了会怎么样：角色声明不登记，config_lines 里就少了 define 角色，
            台词里的角色变量变成未定义。
        被谁调用：`emit()` 按 k=="define" 分派。
        """
        if s.get("name"):
            self.char_var(s["name"])
            self.stats["角色声明"] += 1

    # --- 立绘 ---
    def do_sprite(self, s, depth, lines):
        """把 S.sprite / S.show 立绘语句翻译成 `show 立绘名 at 站位`。

        干什么：解析立绘的路径、tag、pos，通过 `sprite_name()` 拿到（或新建）
            image 定义，输出 `show <tag variant>`。站位 pos 若命中 Ren'Py 内置
            transform（POS_OK）就加 `at <pos>`，否则按 center 处理并记 todo 提示。
            同时维护 tags_live（当前在场立绘 tag 列表），供后续 hide 使用。
        参数：
            s      sprite 语句字典，含 path / kwargs(tag,pos) / args。
            depth  缩进深度。
            lines  输出行列表（原地追加 show 行）。
        返回：无。
        删了会怎么样：所有立绘 show 都转不出来，Ren'Py 版里角色站不出来。
        被谁调用：`emit()` 按 k=="sprite" 分派。
        """
        pad = "    " * depth
        path = s.get("path") or ""
        kw = s.get("kwargs") or {}
        args = s.get("args") or []
        tag = kw.get("tag") or os.path.splitext(
            os.path.basename(path.replace("\\", "/")))[0]
        pos = str(kw.get("pos") or (args[1] if len(args) > 1 else "center")).lower()
        full = self.sprite_name(tag, path)
        tag_s = full.split(" ")[0]
        out = "%sshow %s" % (pad, full)
        if pos in POS_OK:
            out += " at %s" % pos
        elif pos and pos not in self.warned_pos:
            self.warned_pos.add(pos)
            self.todo.append((s.get("line"), "站位 %s Ren'Py 没有对应 transform，"
                                             "已按 center 处理" % pos, path))
            out += " at center"
        lines.append(out)
        if tag_s not in self.tags_live:
            self.tags_live.append(tag_s)
        self.stats["立绘"] += 1

    # --- 背景 / 叠加图 ---
    def do_bg(self, s, depth, lines):                       # 不会直接出现
        """占位：STMG 没有独立的 bg 语句类型（背景走 S.cg/S.bg），这里永不触发。

        干什么：类型分派表里保留的一个空实现——STMG 的剧本里没有 k=="bg"
            这种语句（换背景统一由 `do_call()` 的 S.cg/S.bg/S.background 分支
            处理），所以这个方法永远不该被 emit 调到。留着是为了 k=="bg"
            万一出现时不至于落到「不认识」分支里误报警。
        参数：s / depth / lines 同其它 do_*。
        返回：无（什么都不做）。
        """
        pass

    def do_picture(self, s, depth, lines):
        """处理 S.picture：叠加一张贴图（有 path 就 show，没有就 hide 当前贴图）。

        干什么：STMG 的 `S.picture("png/x.png")` 在当前立绘之上叠一张图，
            不带参数调用则收起当前贴图。这里通过 `pic_image()` 拿 image 名，
            有 path 就输出 `show pic_xxx`，无 path 且当前有 pic_name 就输出
            `hide pic_xxx` 并清空记录，同时累加「贴图」统计。
        参数：
            s      picture 语句字典，含可选 path。
            depth  缩进深度。
            lines  输出行列表（原地追加 show/hide）。
        返回：无。
        删了会怎么样：叠加图（对话框插图、特效图等）在 Ren'Py 版里出不来/收不掉。
        被谁调用：`emit()` 按 k=="picture" 分派；`do_call()` 的 S.picture 分支
            也会直接调它（传 {"path": a0}）。
        """
        pad = "    " * depth
        if s.get("path"):
            self.pic_name = self.pic_image(s["path"])
            lines.append("%sshow %s" % (pad, self.pic_name))
        elif self.pic_name:
            lines.append("%shide %s" % (pad, self.pic_name))
            self.pic_name = None
        self.stats["贴图"] += 1

    # --- 变量 ---
    def do_set(self, s, depth, lines):
        """处理 SET 变量 = 值：翻译成 Ren'Py 的 `$ 变量 = 值`。

        干什么：普通变量赋值 → `$ sanitize(name) = map_store(expr)`。
            两个特例：1) `STM.Q = ...` 是「输入提示语」，不输出赋值，只记到
            last_q 供后续 Question 复用；2) `STM.*` 其它只读命名空间变量赋值
            Ren'Py 里没有对应，输出注释 + 记 todo 跳过。
        参数：
            s      set 语句字典，含 name / expr。
            depth  缩进深度。
            lines  输出行列表（原地追加 $ 行或注释）。
        返回：无。
        删了会怎么样：所有 SET 赋值都转不出来，Ren'Py 版里变量全空、逻辑错乱。
        被谁调用：`emit()` 按 k=="set" 分派。
        """
        pad = "    " * depth
        name = s["name"]
        expr = s["expr"]
        if name.upper() == "STM.Q":
            self.last_q = expr
            self.stats["输入提示"] += 1
            return
        if name.upper().startswith("STM."):
            lines.append("%s# [没转] %s = %s（STM 命名空间只读，Ren'Py 里没有对应）"
                         % (pad, name, expr))
            self.todo.append((s.get("line"), "STM 内部变量赋值无法转换", name))
            return
        lines.append("%s$ %s = %s" % (pad, sanitize(name, "var"), map_store(expr)))
        self.stats["赋值"] += 1

    # --- 输入 ---
    def do_question(self, s, depth, lines):
        """处理 Question：翻译成 `$ stmg_answer = renpy.input(prompt)`。

        干什么：STMG 的 Question 让玩家输入文字，结果存进 STM.ANSWER。Ren'Py
            里对应 `renpy.input()`，结果塞进 stmg_answer（和 map_store 的映射一致）。
            提示语 prompt 优先用语句自带的，没有就退化用上一条 STM.Q 存的提示，
            再没有就用「请输入」兜底；prompt 含拼接/STM 变量时先过 say_text 处理。
        参数：
            s      question 语句字典，含可选 prompt。
            depth  缩进深度。
            lines  输出行列表（原地追加 $ renpy.input 行）。
        返回：无。
        删了会怎么样：所有让玩家输入文字的环节（起名、答题）都转不出来。
        被谁调用：`emit()` 按 k=="question" 分派。
        """
        pad = "    " * depth
        prompt = s.get("prompt") or self.last_q or ""
        if is_str_literal(prompt):
            text = lit(md2rpy(prompt[1:-1]))
        elif "+" in prompt or "STM." in prompt:
            pre, text = self.say_text(prompt, s.get("line"), depth)
            lines.extend(pre)
        else:
            text = lit(prompt or "请输入")
        lines.append("%s$ stmg_answer = renpy.input(%s, length=40)"
                     % (pad, text))
        self.stats["玩家输入"] += 1

    # --- 条件 ---
    def do_if(self, s, depth, lines):
        """处理 If 条件分支：翻译成 Ren'Py 的 `if ...:` + 缩进 body（+ 可选 else）。

        干什么：条件分两类写法——1) STMG 的 `If "选项名"`（字符串字面量条件）
            翻成 `"选项名" in stmg_chosen`（查玩家选过集合）；2) 普通表达式条件
            过 `map_store()` 换名字后原样用。然后递归 `emit()` 翻译 body，
            有 else_body 就补 `else:`。累加「条件分支」统计。
        参数：
            s      if 语句字典，含 cond / body / else_body。
            depth  缩进深度。
            lines  输出行列表（原地追加 if/else 行 + 递归 body）。
        返回：无。
        删了会怎么样：所有分支剧情（多结局、选项后果）在 Ren'Py 版里全塌成直线。
        被谁调用：`emit()` 按 k=="if" 分派。
        """
        pad = "    " * depth
        cond = (s.get("cond") or "").strip()
        if is_str_literal(cond):
            expr = '"%s" in stmg_chosen' % cond[1:-1]
        else:
            expr = map_store(cond) or "True"
        lines.append("%sif %s:" % (pad, expr))
        self.emit(s.get("body") or [], depth + 1, lines)
        eb = s.get("else_body") or []
        if eb:
            lines.append("%selse:" % pad)
            self.emit(eb, depth + 1, lines)
        self.stats["条件分支"] += 1

    def do_else(self, s, depth, lines):
        """落单的 Else：STMG 里没有独立的 else 语句，这里只报警不输出。

        干什么：STMG 的 else 一定跟在 If 后面，不会单独出现；如果解析层真冒出
            一个 k=="else" 的语句（说明剧本写法异常），这里不强行生成 Ren'Py
            的 else（会和前面的 if 对不上），只记进 todo 标「已跳过」，避免
            生成语法错位的 else 块。
        参数：
            s      else 语句字典，含 line。
            depth  缩进深度（本函数不输出行）。
            lines  输出行列表（本函数不追加）。
        返回：无。
        删了会怎么样：异常剧本里的孤立 else 会被静默忽略，但反正本就转不了，
            影响只限于少一条提醒。
        被谁调用：`emit()` 按 k=="else" 分派。
        """
        self.todo.append((s.get("line"), "落单的 Else（前面没有 If），已跳过", "Else:"))

    # --- 选择支 ---
    def do_choose(self, s, depth, lines):
        """把 Choose 选择支翻译成 Ren'Py 的 `menu:` 块。

        干什么：每条选项输出一行 `"选项文字":`，紧接一行 `$ stmg_chosen.add("选项文字")`
            把玩家选了啥记进集合（供后续 `If "选项名"` 查）。选项文字过
            `md2rpy()` 处理富文本标记。完全没有选项时生成一个空 menu（提示人工处理）。
            累加「选择支」统计。
        参数：
            s      choose 语句字典，含 options（选项文字列表）。
            depth  缩进深度。
            lines  输出行列表（原地追加 menu 块）。
        返回：无。
        删了会怎么样：所有分支选项在 Ren'Py 版里消失，玩家没得选、剧情无分支。
        被谁调用：`emit()` 按 k=="choose" 分派。
        """
        pad = "    " * depth
        self.menu_n += 1
        opts = s.get("options") or []
        lines.append("%smenu:" % pad)
        for o in opts:
            lines.append('%s    %s:' % (pad, lit(md2rpy(o))))
            lines.append('%s        $ stmg_chosen.add(%s)' % (pad, lit(o)))
        if not opts:
            lines.append("%s    \"（空选择支）\":" % pad)
            lines.append("%s        pass" % pad)
        self.stats["选择支"] += 1

    # --- 标签 ---
    def do_label(self, s, depth, lines):
        """处理 label：翻译成 `label 名:`，但有两个特殊约定。

        干什么：1) 嵌套在分支里（depth>1）的 label Ren'Py 不支持，记 todo 跳过；
            2) 名为 start 的 label 由 `run()` 统一生成，这里直接跳过不重复输出；
            3) 其余 label 过 `sanitize()` 清洗成合法名后输出 `label xxx:`。
        参数：
            s      label 语句字典，含 name。
            depth  缩进深度（用于判断是不是嵌套 label）。
            lines  输出行列表（原地追加 label 行或注释）。
        返回：无。
        删了会怎么样：跳转目标 label 不生成，所有 S.jump 找不到落点、转不出来。
        被谁调用：`emit()` 按 k=="label" 分派。
        """
        name = s.get("name") or ""
        if depth > 1:
            self.todo.append((s.get("line"), "嵌套在分支里的 label Ren'Py 不支持，已跳过",
                              name))
            return
        if name.lower() == "start":
            return                       # start 由调用方统一处理
        lines.append("label %s:" % sanitize(name, "label"))

    # --- stm.os ---
    def do_stm_os(self, s, depth, lines):
        """stm.os 受控文件操作：Ren'Py 没有对应功能，标成待办注释。

        干什么：STMG 的 `stm.os(...)` 是引擎内部的受控文件读写（沙箱化），
            Ren'Py 里没有等价物，没法自动翻。这里输出一行 `# [没转] stm.os ...`
            注释，并把原样调用记进 todo，留给人手工用 Ren'Py 的文件 API 实现。
        参数：
            s      stm_os 语句字典，含 op / path / line。
            depth  缩进深度。
            lines  输出行列表（原地追加注释）。
        返回：无。
        删了会怎么样：文件操作相关的剧情逻辑在导出后无痕消失，且没人知道缺了。
        被谁调用：`emit()` 按 k=="stm_os" 分派。
        """
        pad = "    " * depth
        lines.append("%s# [没转] stm.os %s(%s)", )
        lines[-1] = "%s# [没转] stm.os %s(%s)" % (pad, s.get("op"), s.get("path"))
        self.todo.append((s.get("line"),
                          "stm.os 受控文件操作 Ren'Py 没有对应功能",
                          "stm.os(%s(\"%s\"))" % (s.get("op"), s.get("path"))))
        self.stats["stm.os（未转）"] += 1

    # --- 函数调用 ---
    def do_call(self, s, depth, lines):
        """把 S.xxx / STM.xxx / R.xxx 函数调用翻译成对应的 Ren'Py 写法。

        干什么：STMG 的「函数调用」是命令最密集的一类，按调用对象分三大支：
            * obj=="S"：cg/bg/background→scene、picture→show 贴图、play→play music、
              sound→play sound、voice→voice、stop→stop music/sound/voice、hide→hide
              立绘/贴图、jump→jump label、end→jump stmg_ending、character→标 todo、
              其它未实现→注释。
            * obj=="STM"：display→renpy.notify，其它→注释待办。
            * obj=="R"：api→注释（建议 renpy.fetch），记未转统计。
            任何分支没对应实现都输出 `# [没转]` 注释并记 todo，绝不丢语句。
        参数：
            s      call 语句字典，含 obj / method / args / kwargs。
            depth  缩进深度。
            lines  输出行列表（原地追加各种 Ren'Py 行/注释）。
        返回：无。
        删了会怎么样：换背景、播音乐、立绘显隐、跳转、结束……所有命令语句全转
            不出来，导出的剧本几乎是空的。
        被谁调用：`emit()` 按 k=="call" 分派。
        """
        obj = (s.get("obj") or "").upper()
        m = s["method"].lower()
        pad = "    " * depth
        args = s.get("args") or []
        kw = s.get("kwargs") or {}
        a0 = args[0] if args else ""

        if obj == "S":
            if m in ("cg", "bg", "background"):
                self.tags_live = []
                if a0:
                    self.bg_name = self.bg_image(a0)
                    lines.append("%sscene %s" % (pad, self.bg_name))
                else:
                    self.bg_name = None
                    lines.append("%sscene black" % pad)
                self.stats["换背景"] += 1
            elif m == "picture":
                self.do_picture({"path": a0}, depth, lines)
            elif m == "play":
                loop = str(kw.get("loop", "true")).lower() not in ("false", "0", "no")
                lines.append("%splay music %s%s"
                             % (pad, lit(self.asset_ref(a0)), "" if loop else " noloop"))
                self.stats["BGM"] += 1
            elif m == "sound":
                lines.append("%splay sound %s" % (pad, lit(self.asset_ref(a0))))
                self.stats["音效"] += 1
            elif m == "voice":
                lines.append("%svoice %s" % (pad, lit(self.asset_ref(a0))))
                self.stats["语音"] += 1
            elif m == "stop":
                what = (a0 or "bgm").lower()
                if what in ("bgm", "music", "all"):
                    lines.append("%sstop music" % pad)
                if what in ("sound", "se", "all"):
                    lines.append("%sstop sound" % pad)
                if what in ("voice", "all"):
                    lines.append("%sstop voice" % pad)
                self.stats["停音频"] += 1
            elif m == "hide":
                what = (a0 or "sprite").lower()
                if what in ("picture", "pic"):
                    if self.pic_name:
                        lines.append("%shide %s" % (pad, self.pic_name))
                        self.pic_name = None
                elif what == "sprite":
                    for t in self.tags_live:
                        lines.append("%shide %s" % (pad, t))
                    self.tags_live = []
                elif what == "all":
                    for t in self.tags_live:
                        lines.append("%shide %s" % (pad, t))
                    self.tags_live = []
                    if self.pic_name:
                        lines.append("%shide %s" % (pad, self.pic_name))
                        self.pic_name = None
                else:
                    tag_s = sanitize(what, "sprite")
                    lines.append("%shide %s" % (pad, tag_s))
                    if tag_s in self.tags_live:
                        self.tags_live.remove(tag_s)
                self.stats["隐藏图层"] += 1
            elif m == "jump":
                if a0 in self.labels:
                    lines.append("%sjump %s" % (pad, sanitize(a0, "label")))
                else:
                    lines.append("%s# [没转] S.jump(\"%s\") 找不到这个标签" % (pad, a0))
                    self.todo.append((s.get("line"), "跳转的标签不存在",
                                      "S.jump(\"%s\")" % a0))
                self.stats["跳转"] += 1
            elif m == "end":
                lines.append("%sjump stmg_ending" % pad)
                self.stats["结束"] += 1
            elif m == "character":
                self.todo.append((s.get("line"), "S.character 参数看不懂，已跳过",
                                  str(s)))
            else:
                lines.append("%s# [没转] S.%s(...)" % (pad, s["method"]))
                self.todo.append((s.get("line"), "没实现的内建函数",
                                  "S.%s(...)" % s["method"]))

        elif obj == "STM":
            if m == "display":
                lines.append("%s$ renpy.notify(%s)" % (pad, lit(strip_quotes(a0))))
                self.stats["提示"] += 1
            else:
                lines.append("%s# [没转] STM.%s(...)" % (pad, s["method"]))
                self.todo.append((s.get("line"), "STM.%s 没有对应实现" % s["method"],
                                  str(s)))

        elif obj == "R":
            lines.append("%s# [没转] R.api(url=%s) —— Ren'Py 里请用 renpy.fetch() 自己写"
                         % (pad, kw.get("url") or a0))
            self.todo.append((s.get("line"), "R.api 联网请求无法自动转换；"
                                             "Ren'Py 可用 renpy.fetch(url) 替代",
                              "R.api(url=\"%s\")" % (kw.get("url") or a0)))
            self.stats["R.api（未转）"] += 1

        else:
            lines.append("%s# [没转] %s.%s(...)" % (pad, obj, s["method"]))
            self.todo.append((s.get("line"), "不认识的调用", str(s)))

    # ---------------- 顶层 ---------------- #
    def run(self):
        """生成剧本正文 script.rpy 的全部行。

        干什么：1) 先 walk 整个脚本收集所有 label 名（供 jump 判断落点）；
            2) 从 body 里剥掉第一个 start label（统一在下面写 label start:）；
            3) 调 `emit()` 翻译正文；4) 结尾按有没有 ending 决定 `jump stmg_ending`
            还是 `return`；5) 若有 ending 段，单独生成 label stmg_ending: 块。
        参数：无（读 self.script / self.labels）。
        返回：字符串行列表（不含结尾换行），直接 "\n".join 写文件。
        删了会怎么样：整个剧本正文生不出来，导出没有 script.rpy。
        被谁调用：main()（conv.run() 拿到 body 行）。
        """
        body = list(self.script.body)
        # 收集所有 label，方便判断 jump 目标
        for s in self.script.walk():
            if s["k"] == "label" and s.get("name"):
                self.labels.add(s["name"])
        self.labels.add("Start")

        lines = ["## 本文件由 tools/stm2renpy.py 从 %s 自动生成"
                 % os.path.basename(self.script.path), ""]

        has_start = bool(body) and body[0]["k"] == "label" \
            and (body[0].get("name") or "").lower() == "start"
        if has_start:
            body = body[1:]
        lines.append("label start:")
        self.emit(body, 1, lines)
        lines.append("")
        lines.append("    jump stmg_ending" if self.script.ending else "    return")

        if self.script.ending:
            lines.append("")
            lines.append("label stmg_ending:")
            self.emit(self.script.ending, 1, lines)
            lines.append("    return")
        return lines

    def config_lines(self):
        """生成 stmg_config.rpy 的全部行（标题/分辨率/角色/image/兼容变量）。

        干什么：输出 Ren'Py 工程配置：config.name / version、gui.init 基准分辨率、
            STMG 运行时变量（stmg_answer / stmg_os / ... / stmg_chosen 集合）、
            字体提示注释；再按 char_order 输出每个角色的 `define X = Character(...)`，
            按 self.images 输出所有 image 定义。所有内容纯文本拼装，不碰磁盘。
        参数：无（读 self.script.header / self.char_order / self.chars / self.images）。
        返回：字符串行列表（不含结尾换行），直接写 stmg_config.rpy。
        删了会怎么样：导出的工程没有角色定义、没有 image 定义、没有兼容变量，
            script.rpy 里引用的全是未定义的东西，Ren'Py 直接报错。
        被谁调用：main()（conv.config_lines() 拿到配置行）。
        """
        h = self.script.header
        out = ["## 本文件由 tools/stm2renpy.py 自动生成",
               "## 标题 / 分辨率 / 角色 / 图像定义 / STMG 运行时兼容变量",
               "",
               'define config.name = _("%s")' % (h.get("title") or self.name),
               'define config.version = "%s"' % (h.get("ver") or "1.0.0"),
               "",
               "## 基准分辨率（你的 Ren'Py 工程已经配好了就删掉这两行）",
               "init python:",
               "    gui.init(%d, %d)" % (self.script.width, self.script.height),
               "",
               "## 字体：STMG 写的是字体名，Ren'Py 要的是字体文件。",
               "## 想保持一致就把字体文件放进 game/fonts/，再取消下面两行的注释。",
               '## define gui.text_font = "fonts/你的字体.ttf"',
               '## define gui.name_text_font = "fonts/你的字体.ttf"',
               "",
               "## STMG 运行时变量（剧本里 STM.ANSWER / STM.OS / STM.API 的落点）",
               'default stmg_answer = ""',
               'default stmg_os = ""',
               "default stmg_api = None",
               'default stmg_name = ""',
               'default stmg_q = ""',
               "## 记录玩家选过哪些选项——STMG 的 If \"选项名\" 就是查这个",
               "default stmg_chosen = set()",
               ""]

        if self.char_order:
            out.append("## 角色（来自 S.character(\"名字\")）")
            for disp in self.char_order:
                out.append('define %s = Character("%s")'
                           % (self.chars[disp], disp.replace('"', '\\"')))
            out.append("")

        if self.images:
            out.append("## 图像定义（来自 S.cg / S.character(立绘) / S.picture）")
            out.extend(sorted(self.images.values()))
            out.append("")
        return out


# --------------------------------------------------------------------------- #
# 素材 / 报告
# --------------------------------------------------------------------------- #
def human(n):
    """把字节数格式化成带单位的可读字符串（B/KB/MB/GB/TB）。

    干什么：转换报告里要显示拷贝了多少素材、占多大体积，这里把裸字节数
        转成「12.3 MB」这种人看得懂的格式（1024 进位）。
    参数：n  字节数（int / float）。
    返回：形如 "12.3 MB" / "1.1 GB" 的字符串。
    删了会怎么样：报告里素材体积只能显示一堆裸数字，不直观（但功能不影响）。
    被谁调用：main()（打印「复制 N 个文件，X」那行）。
    """
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f TB" % n


def copy_assets(proj_dir, game_dir, conv):
    """按 conv 登记好的落点拷素材，引用路径和磁盘路径保证一致。"""
    n, total = 0, 0
    for rel, dst_rel in sorted(conv.assets.items()):
        src = os.path.join(proj_dir, rel.replace("/", os.sep))
        if not os.path.isfile(src):
            continue                    # 剧本引用了但磁盘上没有这个文件
        dst = os.path.join(game_dir, dst_rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        n += 1
        total += os.path.getsize(dst)
    return n, total


def main(argv):
    """命令行入口：把一个 STMG 项目转成能塞进 Ren'Py SDK 跑的工程。

    干什么：解析参数（源项目 / --out / --title / --no-assets）→ 读 script.stm
        → 校验无错 → 建 Conv 跑翻译 → 写出 game/script.rpy 和 game/stmg_config.rpy
        → 按需拷贝素材到 images/audio/ → 写「转换报告.md」（统计 + 待手工处理清单）
        → 打印结果摘要。任何一步失败（无参数/找不到剧本/剧本有错）都返回非 0。
    参数：argv  sys.argv（argv[0] 是脚本名，从 argv[1] 起是参数）。
    返回：进程退出码（0 成功 / 2 用法或输入错误）。
    被谁调用：模块末尾 `if __name__ == "__main__": sys.exit(main(sys.argv))`。
    """
    args = argv[1:]
    if not args:
        print(__doc__)
        return 2

    src = os.path.abspath(args[0])
    out = None
    title = None
    do_assets = True

    i = 1
    while i < len(args):
        a = args[i]
        if a == "--out":
            i += 1
            out = args[i]
        elif a == "--title":
            i += 1
            title = args[i]
        elif a == "--no-assets":
            do_assets = False
        i += 1

    script_path = src if os.path.isfile(src) else os.path.join(src, "script.stm")
    if not os.path.isfile(script_path):
        print("找不到剧本：%s" % script_path)
        return 2
    proj_dir = os.path.dirname(os.path.abspath(script_path))
    name = os.path.basename(proj_dir)

    script = parser.parse_file(script_path)
    if script.error_count():
        print("剧本有 %d 个错误，先修好再转（用 tools/check.py 看详情）："
              % script.error_count())
        for it in script.issues[:10]:
            print("   %s" % it)
        return 2

    if title:
        script.header["title"] = title

    out = os.path.abspath(out or os.path.join(ROOT, "dist", "%s_renpy" % name))
    game = os.path.join(out, "game")
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(game)

    conv = Conv(script, name, proj_dir)
    conv.scan_assets()
    body_lines = conv.run()
    cfg_lines = conv.config_lines()

    with open(os.path.join(game, "stmg_config.rpy"), "w", encoding="utf-8") as f:
        f.write("\n".join(cfg_lines) + "\n")
    with open(os.path.join(game, "script.rpy"), "w", encoding="utf-8") as f:
        f.write("\n".join(body_lines) + "\n")

    if do_assets:
        n, total = copy_assets(proj_dir, game, conv)
        print("素材　　：复制 %d 个文件，%s" % (n, human(total)))
    else:
        print("素材　　：已跳过（--no-assets）")

    # 报告
    with open(os.path.join(out, "转换报告.md"), "w", encoding="utf-8") as f:
        f.write("# STMG → Ren'Py 转换报告\n\n")
        f.write("来源：`%s`\n\n输出：`%s`\n\n" % (script_path, out))
        f.write("## 转换统计\n\n| 项目 | 数量 |\n|---|---|\n")
        for k, v in conv.stats.most_common():
            f.write("| %s | %d |\n" % (k, v))
        f.write("| 角色 | %d |\n| 图像定义 | %d |\n\n"
                % (len(conv.chars), len(conv.images)))
        f.write("## 怎么用\n\n")
        f.write("1. 装好 Ren'Py SDK，新建一个空工程\n"
                "2. 把这里 `game/` 下的 `script.rpy` / `stmg_config.rpy` / "
                "`images/` / `audio/` 拷进工程的 `game/`\n"
                "3. 用 Ren'Py SDK 启动一次即可\n\n")
        f.write("## 需要手工处理的\n\n")
        if not conv.todo:
            f.write("没有。全部转换成功。\n")
        else:
            f.write("| 行 | 原因 | 原文 |\n|---|---|---|\n")
            for ln, why, text in conv.todo:
                f.write("| %s | %s | `%s` |\n"
                        % (ln or "-", why, str(text).replace("|", "\\|")))
        f.write("\n## 已知差异\n\n")
        f.write("- STMG 的 `If \"选项名\"` 在 Ren'Py 里靠 `stmg_chosen` 集合实现，"
                "语义一致\n"
                "- STMG 没有转场，Ren'Py 有；想加 `with dissolve` 得自己写\n"
                "- `stm.os` 受控文件操作、`R.api` 联网、`STM.python` 扩展库"
                "没有对应实现，已标成注释\n"
                "- 等宽标记 `` `x` `` 去掉了反引号（Ren'Py 没有等宽 text tag）\n"
                "- 打字机、快进、存读档这些用的是 Ren'Py 自带界面，"
                "STMG 的 gui/ 皮肤不会带过来\n")

    print("-" * 56)
    print("剧本　　：%s" % os.path.join(game, "script.rpy"))
    print("配置　　：%s" % os.path.join(game, "stmg_config.rpy"))
    if conv.todo:
        print("要手工处理 %d 处，清单见 转换报告.md" % len(conv.todo))
    else:
        print("全部转换成功，没有遗留。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
