# -*- coding: utf-8 -*-
"""STMG AVG 绘图系统（第 3 期新增）—— 剧本里的「画图/画形状」引擎核心。

这个模块是整个 AVG 系统的**纯计算核心**：只负责「把绘图指令变成几何图形」，
不依赖 pygame、不依赖浏览器——桌面版（pygame）和网页版（canvas）都 import
同一份代码来算几何，保证两边画出来的东西一模一样。

实际「把几何画到屏幕上」的代码在两处：
    桌面版：stmg/render.py 的 draw_avg()（用 pygame 画）
    网页版：stmg/webplayer.html 里的 applyAvg()/runTurtle()（用 canvas 画）
    （网页版没法 import 这份 Python，所以 JS 里有一份逐行对齐的翻译版，
      改这里的规则时务必同步改 webplayer.html 里的 runTurtle！）

==========================================================================
剧本语法（在 .stm 剧本里这样写）
==========================================================================

1) 坐标系
    游戏画面有一个坐标系，(x:0, y:0) 是画面的**正中间**；
    x 向右为正，y 向上为正（数学课本的习惯）。
    例如 1280x720 的窗口：右下角大约是 (640, -360)。

2) 放一个形状
    S.AVG-button(x:100, y:50, "box")
    S.AVG-button(-200, 0, "circle", color="#ff5577", size=120)
    S.AVG-button(0, 0, "我的画")          ← 「我的画」是下面 SET 定义的
    - 前两个参数是坐标（写 x:/y: 或直接按顺序写都行）；
    - 第三个参数是形状名：
        "box"      方框（内置）
        "circle"   圆圈（内置）
        其他名字   必须是 SET 定义的绘图变量（见下），没定义就不画；
    - 可选参数：
        color="#rrggbb"  线的颜色（默认白色）
        size=数字         内置形状的大小：box 是边长、circle 是直径（默认 64）
        width=数字        线宽（默认 3）

3) 用 SET 定义自己的画（海龟绘图，和 LOGO 的小海龟一个思路）
    SET 三角形:
        go(100px)
        left(120)
        go(100px)
        left(120)
        go(100px)
    然后就能 S.AVG-button(0, 0, "三角形") 把它画在画面正中。
    一支看不见的「笔」从 (0,0) 出发、默认朝右、默认落笔（移动会画线）：
        go(距离)      前进（距离可以带 px，如 go(10px)）
        back(距离)    后退
        left(角度)    左转（逆时针，单位度）
        right(角度)   右转（顺时针）
        up()          抬笔（之后移动不画线）
        down()        落笔（恢复画线）
    额外送的几支（超出用户清单的扩展，不写就不用）：
        goto(x, y)    跳到指定点（落笔状态会拖出一条线）
        color("#rrggbb")  换颜色
        width(数字)       换线宽
        circle(半径)      在当前位置画一个圆

4) 清屏
    S.AVG-clear()   ← 把 AVG 画的所有东西全部擦掉

==========================================================================
内部数据格式（别的模块怎么消费这里的输出）
==========================================================================

* 绘图指令 ops：列表里的每一项是 ["指令名", 参数]，例如
      [["go", 100.0], ["left", 120.0], ["up"], ["goto", [10.0, 20.0]]]
  纯 JSON，能直接塞进网页版的 <script> 里。

* 几何结果 geometry：run_turtle() / item_geometry() 的返回值，
      {"strokes": [{"c": 颜色, "w": 线宽, "pts": [x1,y1, x2,y2, ...]}, ...],
       "circles": [{"c": 颜色, "w": 线宽, "cx": x, "cy": y, "r": 半径}, ...]}
  坐标是**局部数学坐标**（y 向上、原点在 S.AVG-button 指定的落点）。
  渲染层拿到后自己翻成屏幕坐标：
      屏幕 x = 画面宽/2 + 局部 x
      屏幕 y = 画面高/2 - 局部 y        ← 注意 y 要翻转！
"""

import math
import re

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 引擎内置的形状名。S.AVG-button 的第三个参数是这些名字时直接用内置几何，
# 是别的名字时去 Runtime 的 avg_shapes 表里找 SET 定义的绘图指令。
PRIMITIVES = ("box", "circle")

# 用户什么都没配的时候用的默认值
DEFAULT_COLOR = "#ffffff"     # 默认线色：白
DEFAULT_SIZE = 64.0           # 默认形状大小（box 边长 / circle 直径），像素
DEFAULT_WIDTH = 3             # 默认线宽，像素

# 一行绘图指令长什么样：go(10px) / left(90) / up() / goto(3,4) ...
OP_LINE_RE = re.compile(r"^([A-Za-z_]\w*)\s*\(\s*(.*?)\s*\)\s*$")
# 一个「数」长什么样：10 / -3.5 / 10px（px 后缀可选，大小写不限）
NUM_RE = re.compile(r"^(-?\d+(?:\.\d+)?)(?:px)?$", re.I)
# 颜色长什么样：#abc 或 #aabbcc（别的不认，写错会报 Issue）
COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# SET 绘图块里允许出现的指令名 -> 参数要求。
#   "num"   一个数（可带 px）
#   "angle" 一个数（度数，不允许 px，但解析上和 num 一样，兼容写法）
#   "none"  括号里必须为空：up() / down()
#   "xy"    两个数，逗号隔开：goto(10, 20)
#   "color" 一个 #开头的颜色
# 参数要求在解析期（parser.py）就检查，写错了直接在 check 阶段报出来，
# 不会拖到玩家玩到一半才炸。
OP_SPEC = {
    "go": "num", "back": "num", "left": "angle", "right": "angle",
    "up": "none", "down": "none",
    "goto": "xy", "color": "color", "width": "num", "circle": "num",
}


# ---------------------------------------------------------------------------
# 小工具：解析数字和颜色
# ---------------------------------------------------------------------------
def parse_num(text, default=0.0):
    """把 "10px" / "-3.5" / "10" 解析成 float。

    解析不出东西（空串、写成了 "abc"）时返回 default —— 绘图指令里写错
    数字不该让整个游戏崩掉，退回默认值继续跑。
    """
    m = NUM_RE.match(str(text or "").strip())
    if not m:
        return float(default)
    return float(m.group(1))


def hex_to_rgb(color, default=(255, 255, 255)):
    """把 "#ffffff" / "#fff" 变成 pygame 要的 (r, g, b) 元组。

    只有桌面版渲染（render.py 的 draw_avg）用得到——网页版的 canvas
    直接吃 "#ffffff" 字符串，不用转。
    认不出（空串、写错）返回 default，别让一个颜色写错弄崩渲染。
    """
    s = str(color or "").strip()
    m = COLOR_RE.match(s)
    if not m:
        return default
    s = s[1:]                       # 去掉开头的 #
    if len(s) == 3:                 # #abc -> #aabbcc，每位重复一次
        s = "".join(ch * 2 for ch in s)
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------------------
# 解析期：把 SET 块里的一行指令编译成 ops 列表的一项
# ---------------------------------------------------------------------------
def compile_op_line(raw):
    """把 SET 绘图块里的一行（如 "go(10px)"）编译成一条指令。

    返回 (指令, 错误信息)：
        成功 -> (["go", 10.0], None)
        失败 -> (None, "人话错误说明")   ← parser 拿它去报 Issue
    指令统一是 [名字, 参数] 的列表（纯 JSON），参数可能是：
        数字（go/back/left/right/width/circle）
        数字对 [x, y]（goto）
        颜色字符串（color）
        什么都不带（up/down，只有一项）
    """
    s = str(raw or "").strip()
    if not s:
        return None, None            # 空行直接跳过，不算错
    m = OP_LINE_RE.match(s)
    if not m:
        return None, "看不懂的绘图指令：%s（应该写成 go(10px) / left(90) 这样的）" % s[:30]
    name = m.group(1).lower()        # GO(10px) 和 go(10px) 等价
    arg = m.group(2).strip()
    spec = OP_SPEC.get(name)
    if spec is None:
        return None, "没有「%s」这条绘图指令（有：%s）" % (
            name, "、".join(sorted(OP_SPEC)))

    if spec == "none":
        # up() / down()：括号里不该有东西；有就提醒（宽容处理，照常执行）
        if arg:
            return None, "%s() 括号里不该写东西，写成 %s() 就行" % (name, name)
        return [name], None

    if spec == "num" or spec == "angle":
        if not NUM_RE.match(arg):
            return None, "%s 的参数应该是一个数（可带 px），这里写的是：%s" % (name, arg[:20])
        return [name, float(NUM_RE.match(arg).group(1))], None

    if spec == "xy":
        parts = [p.strip() for p in arg.split(",") if p.strip()]
        if len(parts) != 2 or not all(NUM_RE.match(p) for p in parts):
            return None, "%s 的参数应该是两个数，逗号隔开（如 %s(10, 20)）" % (name, name)
        return [name, [float(NUM_RE.match(p).group(1)) for p in parts]], None

    if spec == "color":
        c = arg.strip().strip('"')   # 允许写成 color("#ff0000")，引号剥掉
        if not COLOR_RE.match(c):
            return None, "颜色要写成 #rgb 或 #rrggbb（如 #ff5577），这里写的是：%s" % c[:20]
        return [name, c.lower()], None

    return None, None                # 理论上走不到（spec 表写错了才会）


def compile_ops(lines):
    """把 SET 绘图块的全部行编译成 ops 列表。

    返回 (ops, issues)：issues 是 [(行文本, 错误信息), ...]，
    parser 拿它去生成带行号的 Issue。有错的行**跳过不收**，
    这样一处小笔误不至于让整幅画废掉。
    """
    ops, issues = [], []
    for ln in lines:
        op, err = compile_op_line(ln)
        if err:
            issues.append((ln, err))
        elif op is not None:
            ops.append(op)
    return ops, issues


# ---------------------------------------------------------------------------
# 运行期：把绘图指令跑一遍，得到几何图形
# ---------------------------------------------------------------------------
def run_turtle(ops, color=DEFAULT_COLOR, width=DEFAULT_WIDTH):
    """执行海龟绘图指令，返回几何结果（格式见文件头注释）。

    一支看不见的笔：
        位置 (x, y) 从 (0, 0) 出发 —— 就是 S.AVG-button 指定的落点；
        朝向 head，0 度 = 朝右（+x），逆时针为正（和数学课一致）；
        笔状态 pen，True = 落笔（移动会画线），默认就是落笔。
    坐标系是 y 向上的数学坐标，**翻成屏幕坐标是渲染层的活**，这里不管。

    ops 里每条是 [名字, 参数]；不带参数的（up/down）就是 [名字]。
    遇到看不懂的指令直接跳过（解析期已经拦过一遍，这里是双保险，
    比如老存档重放时喂进来的旧数据）。
    """
    x = y = 0.0
    head = 0.0
    pen = True
    cur_color = str(color or DEFAULT_COLOR)
    cur_width = int(width or DEFAULT_WIDTH)

    strokes = []          # 结果：一串折线
    circles = []          # 结果：一串圆
    cur = None            # 当前正在画的折线（换色/换线宽/抬笔时会断开）

    def start_stroke(px, py):
        """开一段新折线（当前颜色/线宽）。"""
        return {"c": cur_color, "w": cur_width, "pts": [px, py]}

    def line_to(nx, ny):
        """从当前位置画线到 (nx, ny)——落笔才真画，抬笔就只挪位置。"""
        nonlocal x, y, cur
        if pen:
            if cur is None:
                cur = start_stroke(x, y)
                strokes.append(cur)
            cur["pts"].extend([nx, ny])
        else:
            cur = None     # 抬笔移动：下一次落笔要另起一段
        x, y = nx, ny

    for op in ops or []:
        name = str(op[0]).lower() if op else ""
        arg = op[1] if len(op) > 1 else None

        if name == "go" or name == "back":
            # 前进/后退：沿当前朝向移动 arg 像素（back 就是负方向）
            d = float(arg or 0.0)
            if name == "back":
                d = -d
            # 三角函数算落点：head=0 朝右，90 度朝上（数学坐标 y 向上）
            import math
            rad = math.radians(head)
            line_to(x + d * math.cos(rad), y + d * math.sin(rad))

        elif name == "left":
            head += float(arg or 0.0)      # 左转 = 逆时针 = 角度加
        elif name == "right":
            head -= float(arg or 0.0)      # 右转 = 顺时针 = 角度减

        elif name == "goto":
            gx, gy = (arg or [0.0, 0.0])[0:2]
            line_to(float(gx), float(gy))

        elif name == "up":
            pen = False
            cur = None                     # 抬笔断开当前折线
        elif name == "down":
            pen = True

        elif name == "color":
            cur_color = str(arg or DEFAULT_COLOR)
            cur = None                     # 换色另起一段，免得一条折线两种色
        elif name == "width":
            cur_width = max(1, int(float(arg or DEFAULT_WIDTH)))
            cur = None
        elif name == "circle":
            # 在笔的当前位置画一个圆（不影响笔的位置和朝向）
            circles.append({"c": cur_color, "w": cur_width,
                            "cx": x, "cy": y, "r": abs(float(arg or 10.0))})

        # 其他名字：跳过（见函数开头的说明）

    return {"strokes": strokes, "circles": circles}


def primitive_geometry(name, size=DEFAULT_SIZE, color=DEFAULT_COLOR,
                       width=DEFAULT_WIDTH):
    """内置形状（box / circle）的几何。

    box    以落点为中心的正方形，边长 size；
    circle 以落点为圆心的圆，直径 size（半径 size/2）。
    不是内置形状返回 None，调用方改走 run_turtle()。
    """
    name = str(name or "").lower()
    s = float(size or DEFAULT_SIZE)
    if name == "box":
        h = s / 2.0
        # 五个点首尾相接画成一个闭合方框
        pts = [-h, -h, h, -h, h, h, -h, h, -h, -h]
        return {"strokes": [{"c": color, "w": int(width or DEFAULT_WIDTH),
                             "pts": pts}], "circles": []}
    if name == "circle":
        return {"strokes": [],
                "circles": [{"c": color, "w": int(width or DEFAULT_WIDTH),
                             "cx": 0.0, "cy": 0.0, "r": s / 2.0}]}
    return None


def item_geometry(item):
    """一条 AVG 场景物品（S.AVG-button 事件存进 scene["avg"] 的 dict）
    -> 几何结果。桌面渲染（render.py）和网页渲染（webplayer.html 的 JS
    翻译版）都按这个语义画。

    item 里可能有：shape（形状名）/ ops（用户绘图的指令）/ x, y（落点，
    这里不用——平移是渲染层的事）/ color / size / width（一次性覆盖默认值）。
    """
    name = str(item.get("shape") or "").lower()
    color = str(item.get("color") or DEFAULT_COLOR)
    width = item.get("width")
    size = item.get("size")

    # 先试内置形状
    geo = primitive_geometry(name, size if size is not None else DEFAULT_SIZE,
                             color, width if width is not None else DEFAULT_WIDTH)
    if geo is not None:
        return geo

    # 不是内置形状：按用户 SET 定义的指令跑一遍。
    # item["ops"] 是 Runtime 在发事件时塞进来的（见 runtime.do_call），
    # 空的说明形状没定义过——返回空几何，什么都不画，也不报错。
    return run_turtle(item.get("ops") or [],
                      color=color,
                      width=width if width is not None else DEFAULT_WIDTH)
