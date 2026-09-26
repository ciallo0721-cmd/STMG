# STMG 开发教程 —— 从目录结构到 AVG 绘图系统

> 本文写给想读懂 STMG 源码、并在这之上继续开发新功能的开发者。
> 阅读顺序就是推荐的学习顺序：先建立全局地图，再逐层深入，
> 最后用「AVG 绘图系统」这个真实的新功能案例，把前面学的所有知识串起来。
>
> STMG（Super Text Markdown Galgame）是一个用 Markdown 风格语法写视觉小说的引擎：
> 剧本用 `.stm` 文本文件写，引擎负责解析、推进、渲染、存档、打包和发布成网页。
> 引擎本体是纯 Python（标准库 + pygame），网页版跑在 WebAssembly 的 CPython 里，
> 和桌面版共享同一套代码——这是整个项目最重要的设计决策，后面会反复提到。

---

## 一、全局地图：目录结构与模块职责

打开仓库，第一层是这样的：

```
STMG/
├── stmg/            引擎本体（Python 包，所有核心逻辑都在这）
├── tools/           命令行工具（检查、体检、自测、打包、发布）
├── demo/            示例项目（demo/script.stm 是标准示例，avg_demo.stm 是 AVG 示例）
├── stmenc/          加密发布器（把项目打成 .stmdec）
├── projects/        用户的游戏项目（gitignore，不进仓库）
├── mod/             美化包（换主题用）
├── start.py         入口：python start.py 项目目录
├── launcher.py      图形化启动器（CustomTkinter）
└── README.md        用户文档（语法手册在这里）
```

`stmg/` 包内部再拆一层，每个文件一条清晰的责任线：

| 文件 | 职责 | 依赖 pygame？ |
|------|------|:---:|
| `parser.py` | 把 .stm 文本解析成语句树（AST） | 否 |
| `runtime.py` | 把 AST 解释成「事件流」（生成器） | 否 |
| `session.py` | 推进器：整理事件、维护场景状态、快照存档 | 否 |
| `render.py` | pygame 绘制函数库（排版、立绘、AVG、转场） | 是 |
| `gui.py` | 游戏窗口主循环、按钮、菜单、存读档界面 | 是 |
| `audio.py` | 三通道音频（BGM / 音效 / 语音） | 是 |
| `save.py` | 存档槽、成就、CG 回廊、设置持久化 | 否 |
| `avg.py` | AVG 绘图系统核心（海龟绘图 → 几何） | 否 |
| `mod.py` | 美化包加载与校验 | 否 |
| `uiconf.py` | 界面配置三层叠加（默认 < 美化包 < custom/gui.py） | 否 |
| `pack.py` | 资源包（stmgpack:/ 前缀的打包素材） | 否 |
| `crypto.py` | .stmdec 加解密（纯标准库） | 否 |
| `stmos.py` | 受控文件操作（DDLC 式演出用，安全围栏） | 否 |
| `stdlib_api.py` | stmg.python 白名单库 + R.api 联网 | 否 |
| `web_bridge.py` | 网页版引擎桥（Pyodide 里跑真引擎） | 否 |
| `webplayer.html` | 网页播放器模板（单文件 HTML） | - |
| `markdown.py` | 台词里的 md 内联标记（粗体/颜色/注音…） | 否 |

**记住这张表的分界线**：不依赖 pygame 的那批文件（parser / runtime / session / avg / save…）
可以在无头环境跑——`start.py --auto` 无头测试、网页版引擎、未来的移植版，全都靠这个性质。
你往引擎里加新功能时，尽量把逻辑放进「无头侧」，渲染层只做「怎么画」，不做「画什么」的决策。

---

## 二、一份剧本的一生：解析器（parser.py）

剧本是纯文本，解析器把它变成一棵语句树。整条流水线是：

```
读文件 → 去注释(<-- -->) → 抠出 python 代码块 → 按 < > 切块
→ 第一块判定为「头部」或「正文」 → 逐行解析成语句树 → 静态体检(_validate)
```

几个关键设计：

**1. 头部判定是「投票制」不是「强制制」。** 第一块里如果出现 `Start:` 标签行或
python 占位符，直接当正文；否则数一数 `名称=值` 行的占比，过半才算头部。
这样头部里写错一行还能按头部报错，而整块剧情不会被误判。

**2. 缩进即分支。** `_parse_lines` 是一个递归下降解析器：`If 条件:` / `Choose:` /
`Repeat N:` / `While 条件:` / `SET 名字:` 后面跟缩进更深的行，就是它们的子块。
缩进突然变浅 = 子块结束。

**3. 正则表就是语法表。** 文件顶部的十几条 `_RE` 常量一一对应语法元素
（`IF_RE`、`CHOOSE_RE`、`SET_RE`、`CALL_RE`……）。想加新语法，先在这里登记。
比如第 3 期新增的 AVG 就加了两条：

- `AVG_SET_RE`：匹配 `SET 名字:`（无等号、带冒号），后面收一个缩进的绘图指令块；
- `CALL_RE` 扩了连字符：`S.AVG-button(...)` 里的 `-` 允许出现在函数名里，
  解析后统一把 `-` 换成 `_`，所以 `AVG-button` 和 `AVG_button` 是同一个函数。

**4. 参数解析容忍两种风格。** `parse_args` 同时认 `key=值` 和 `key:值`
（冒号写法是给 AVG 准备的：`S.AVG-button(x:0, y:0, "box")`）。
唯一的例外是 `http://` —— 冒号后面紧跟 `//` 的不当成 key，避免把 URL 撕碎。

**5. 解析错误进 `issues`，不抛异常。** 每条问题是一个 `Issue(行号, 消息, 建议, 级别)`，
级别分五档。`tools/check.py` 把它们打印出来，游戏内错误界面也会显示——
**剧本写错了玩家不该看到 Python 堆栈**，这是硬规矩。

**6. `include` 是解析期内联。** `include "chapter1.stm"` 在解析期把目标文件的正文
搬进来，带循环检测和文件名前缀的报错。所以主流程里 `include` 的公共段落必须写在
走不到的末尾（配一个 `S.end()`），否则会被执行两遍。

---

## 三、运行时：事件流生成器（runtime.py）

`Runtime.run()` 是一个生成器：`yield` 吐事件，`send()` 收玩家输入。
渲染层不需要懂剧本，剧本不需要懂窗口，中间只传事件字典。事件类型表就写在
runtime.py 的文件头注释里（say / choose / question / bg / sprite / bgm / avg / …）。

`exec_block` 是主循环体：一个 `if/elif` 链按语句类型分发。
`do_call` 处理所有 `S.xxx / STM.xxx / R.xxx` 引擎调用——想加新的 `S.函数`，
就在 `obj == "S"` 分支里加一个 `elif method == "你的函数"`。

三个容易踩的坑：

**① 生成器必须用 `yield from` 串联。** 写成 `for ev in ...: yield ev` 会把
`send()` 的值吞掉，表现为「玩家回答完，下一句台词凭空消失」。

**② 回放机制是一切存档功能的地基。** 读档 = 从头重跑剧本，但把存档里记录的
`answers` 流（选项 / 输入 / 随机数 / api 结果 / os 结果）按序喂回去，
剧情就会走出和存档时一模一样的路。`_take_answer` / `_rand_draw` / `_take_record`
三个函数分别消费三种记录，都是「命中就吃、不命中不越界」的宽容写法——
所以老存档没有新类型的记录也不会错位。

**③ 新增副作用型事件必须登记进 `session.SIDE_EFFECTS`。**
「副作用型」= 不需要等玩家、顺手改变画面/声音的事件（bg、sprite、avg…）。
不登记的话，推进器会把它当成「要等玩家的事件」停在上面，游戏卡死。
这是第 3 期 AVG 实际踩过一次的坑，后面细讲。

---

## 四、推进器与场景状态（session.py）

Session 把事件流整理成玩家友好的形态：

- `session.block` —— 当前要等玩家的那件事（一句台词 / 一组选项 / 一个输入框）；
- `session.scene` —— 当前画面状态字典：`bg / picture / sprites / bgm / avg`；
- `session.effects` —— 本次推进中攒下的副作用事件，渲染层逐条应用。

`_pull()` 会把副作用事件全部吃掉、应用到 scene 上，然后停在下一个玩家事件。
`_apply()` 是 scene 的唯一修改入口：`avg` 事件的 `draw` 就是往
`scene["avg"]` 列表 append 一条形状，`clear` 就是清空列表。

**快照存档**：`snapshot()` 把 answers / say_count / scene / vars / chosen 全部序列化成
纯 JSON（`ensure_ascii=False`）。scene 里能放的东西必须是 JSON 友好类型——
这就是为什么 AVG 形状事件里塞的是「指令列表」而不是 Python 对象。
`restore()` 双轨恢复：先重放对齐执行位置，再用快照覆盖画面与变量
（快照比重放更权威）。老存档（format=1）走原路径，永远向后兼容。

---

## 五、渲染层（gui.py + render.py）

`App.draw_scene()` 决定一帧的图层顺序：

```
背景 bg → 叠图 picture → 立绘 sprites → AVG 绘图层 avg → 对话框文本框
```

每个图层都支持补间动画（带 `dur` 参数时淡入 / 平移，第 2 期加的）。
render.py 里的函数全是「纯绘制」：`draw_sprite / draw_placeholder / draw_avg / draw_transition`，
状态在 session 里，绘制函数不保存任何剧情状态。

**素材缺失不崩**：`load_image` 返回 None 时画占位块。开发期图没画好也能全流程试跑。

### 5.1 补间动画是怎么做的

带 `dur` 参数的立绘 / 背景 / 叠图会平滑过渡而不是瞬切。实现分三步：
推进前 `App._capture_scene()` 先把当前场景快照一份作为动画起点；
副作用应用后对比新旧状态，有差异就登记一条补间（`_setup_anim`）；
每帧绘制时按时间进度 `p`（0 到 1）在起点和终点之间线性插值（`render.lerp`），
立绘的插值由纯函数 `tween_sprite` 完成——位置、缩放、透明度、旋转、
水平站位全部参与插值，所以 `S.character("x.png", pos="right", dur=0.4)`
能看到角色从中间走到右边，而不是闪现过去。

补间状态存在 `self.anim` 字典里，键是立绘 tag 或 `_bg` / `_pic` 这种保留键。
动画是纯视觉层的：session 和存档完全不知道它的存在，所以动画中断、
窗口失焦、读档打断都不会污染剧情状态——这是「渲染层只管怎么画」的好例子。

### 5.2 界面三层叠加（uiconf.py）

界面的外观配置走三层覆盖：引擎内置默认值 → 项目 `custom/gui.py` → 美化包。
`uiconf.setup()` 按顺序读入并合并，任何一层没写的键都沿用上一层。
对话框位置、名字框颜色、标题图、标题曲、立绘站位比例、空闲微动开关……
全在这套配置里。项目作者改 `custom/gui.py` 就能大幅换脸而不碰引擎一行代码；
美化包作者则更进一步，连 CSS / JS（网页版）和主题素材都能换。

调试技巧：`custom/gui.py` 写错了不会白屏——App 初始化时把它包在 try 里，
失败就降级用默认配置，并在开发模式弹一条 toast 告诉你配置错在哪。

---

## 五点五、其余模块深读

### audio.py：三通道音频

BGM、音效、语音各自独立音量、独立通道：`play_bgm` 会做淡入淡出（fade 参数）、
循环控制；`play_se` 不打断 BGM；`play_voice` 是配音专用，带「重听」支持
（语音自动挂载产出的事件带 `auto=True` 和角色 tag，重听功能靠它定位）。
设置面板里三条音量分开滑，玩家关闭 BGM 不影响语音。

**语音自动挂载**是音画分离的好例子：剧本里一句配音都不用写，
只要 `options.stm` 开 `AutoVoice`，引擎按命名约定
`voice/<角色名>/<序号>.wav` 自动找配音、自动播。找不到就静默跳过，
绝不报错——素材是逐渐补齐的，引擎必须容忍「配音还没录」的状态。

### save.py：存档系统与持久化

所有跨会话的数据都走 save.py：存档槽（`slots/` 目录下每槽一个 JSON）、
成就（`achievements.json`）、CG 回廊（`cg.json`）、语言选择、设置。
存档分两代格式：format 1 是老式「answers 流」，format 2 是状态快照
（见第四节）。读档入口先看 format 字段分流，两条路径并存——
这就是「向后兼容」在代码里的长相：不删老路径，新东西并行加。

成就系统值得一提：`STM.achieve("名称")` 触发，第一次解锁才产事件弹窗，
立刻落盘。它跨剧本标题区分——同一项目里不同结局线各自记各自的。

### mod.py 与美化包

美化包 = `mod/<id>/` 下的 `gui.py + theme.css + theme.js + mod.json + 素材`。
modcheck.py 会校验结构完整性、拒绝引用外部 URL（网页版里美化包素材必须本地化，
否则发布器无法打包）。主题 CSS 注入在引擎样式之后，所以直接覆盖即可；
主题 JS 挂在 `STMGTheme` 命名空间下，提供 say / choose / ending 等钩子，
美化包可以监听这些钩子做樱花飘落之类的演出效果。

### pack.py 与资源包

正式发布时素材可以打进一个资源包，运行时用 `stmgpack:/路径` 前缀访问。
`pack.has / pack.open_binary` 是唯二入口，render 的 `load_image` 自动兼容
「散文件」和「包内文件」两种来源。写新渲染代码时不要自己 open 素材文件，
一律走 `render.load_image` 或 `pack.open_binary`，否则资源包模式会读不到。

### crypto.py 与 stmenc：加密发布

`.stmdec` 格式用纯标准库实现：口令派生密钥、内容加密、带篡改校验
（改一个字节都能被发现）。selftest 里有四条对应的测试。要清楚它的定位：
口令最终就写在发布目录的 start.py 里，防的是「玩家随手用记事本打开剧本看结局」，
不是防逆向——这也是 README 里反复强调的诚实声明。

### stmos.py：受控文件操作

`stm.os(read/create/remove/revision)` 让剧本能碰玩家磁盘（DDLC 式演出用），
但围栏极严：只允许四种动作、路径限制在项目目录内、remove 走系统回收站、
revision 自动留 .bak。发布版默认静默，开发模式失败弹 toast。
网页版对应物是 web_bridge 里的 VirtualFS 内存镜像，语义逐条对齐。

### stdlib_api.py：白名单哲学

`stmg.python("math")` 只能开白名单里的库；python 代码块跑在
`SAFE_BUILTINS` 构建的受限环境里——没有 open、没有 eval、没有 import。
`R.api` 是唯一的联网出口，发布版还能用 `allow_net` 一键关死。
给引擎加「能力」时想清楚一件事：能力越多，白名单越要收得越紧。

---

## 六、AVG 绘图系统专题（第 3 期新增）

这是本教程的核心案例：一个从语法到渲染横跨六个文件的新功能。

### 6.1 剧本语法

**坐标系**：`(x:0, y:0)` 是画面正中间，x 向右为正、y 向上为正（数学课本习惯）。
1280x720 的窗口里，右下角约为 `(640, -360)`。

**放形状**：

```stm
S.AVG-button(x:100, y:50, "box")                        ← 冒号坐标写法
S.AVG-button(100, 50, "box")                            ← 顺序坐标写法
S.AVG-button(-200, 0, "circle", color="#ff5577", size=120, width=5)
S.AVG-button(0, 0, "三角形")                             ← 用户定义的形状
S.AVG-clear()                                            ← 整层擦掉
```

形状可以是内置的 `"box"`（方框）或 `"circle"`（圆圈），也可以是下面定义的绘图变量。
可选参数：`color` 线色（#rgb / #rrggbb）、`size` 大小（box 边长 / 圆直径，默认 64）、
`width` 线宽（默认 3）。坐标可以写变量和算式：`SET x = -100` 之后写 `x:x*2`。

**海龟绘图（SET 名字:）**：

```stm
SET 三角形:
    go(120px)      ← 前进（px 后缀可选）
    left(120)      ← 左转 120 度（逆时针）
    go(120px)
    left(120)
    go(120px)      ← 三笔画出一个等边三角形
```

一支看不见的笔从 `(0,0)`（即 S.AVG-button 的落点）出发，默认朝右、默认落笔。
指令集：`go / back / left / right / up / down`（用户需求），外加
`goto(x,y) / color("#..") / width(数字) / circle(半径)` 四个扩展。
写错的指令在**解析期**就被 check 报出来（`parser.py` 调 `avg.compile_ops` 编译并校验），
不会拖到玩家玩到一半才炸。

### 6.2 数据流（六文件协作图）

```
parser.py        avg.py            runtime.py           session.py         渲染层
SET 三角形:  → compile_ops 编译 → avg_shapes 登记    → (不产事件)
S.AVG-button → CALL_RE+parse_args→ 产出 {"t":"avg",…, "ops":[…]} → scene["avg"] 追加
                                                                      ├─ gui.py → render.draw_avg (pygame)
                                                                      └─ webplayer.html → applyAvg (canvas)
```

设计要点：**事件自带全部信息**。`avg_button` 事件里直接塞了 `ops`（绘图指令列表），
渲染层拿到就能画，不用回头问引擎「三角形是什么」。这让网页版省掉一次
Python↔JS 的来回调用，也让存档快照天然可序列化。

### 6.3 avg.py：纯计算核心

avg.py 不依赖 pygame，输出统一的几何格式：

```python
{"strokes": [{"c": "#ffffff", "w": 3, "pts": [x1,y1, x2,y2, ...]}, ...],
 "circles": [{"c": "#ffffff", "w": 3, "cx": 0, "cy": 0, "r": 32}, ...]}
```

坐标是**局部数学坐标**（y 向上，原点在落点）。翻成屏幕坐标是渲染层的活：

```
屏幕 x = 画面宽/2 + 局部 x
屏幕 y = 画面高/2 - 局部 x ← 注意符号！屏幕的 y 轴向下
```

`run_turtle()` 是海龟绘图解释器：维护 `(x, y, head, pen)` 四元状态，
`go` 用三角函数算落点，`left/right` 增减朝向角，`up/down` 切换笔状态，
换色换线宽会断开当前折线另起一段（否则一条 polyline 两种颜色没法画）。

### 6.4 两端渲染

- **桌面**：`render.draw_avg(surface, scene["avg"], W, H)`，pygame 的
  `draw.lines` / `draw.circle` 逐条画。挂在 `draw_scene` 立绘之后、文本框之前。
- **网页**：一块 `<canvas id="l-avg">` 图层（内部分辨率 = 剧本分辨率，随 stage 缩放），
  `applyAvg` 收事件、`drawAvgLayer` 整层重画。因为浏览器跑不了这份 Python，
  webplayer.html 里有一份**逐行对齐的 JS 翻译版**（`avgRunTurtle`）——
  改绘图规则必须两边同步，文件头注释里都写了这条警告。

### 6.5 存档与回放

`avg` 登记进 `SIDE_EFFECTS` 后：读档重放时 avg 事件会被重放并重新应用到
`scene["avg"]`，快照恢复时又用存档瞬间的图层覆盖——两条路都通，
老存档没有 `avg` 键时 `get("avg") or []` 兜底，完全向后兼容。

### 6.6 实战逐行走读：demo/avg_demo.stm 的前八行

把 demo 里的 AVG 示例剧本拆开看，每一行对应引擎里的哪一步：

```stm
S.character("小菲")            ← define 语句：登记角色名（与 AVG 无关，先热身）
SET 三角形:                    ← AVG_SET_RE 命中，进入绘图块收集
    go(120px)                  ← avg.compile_op_line 编译成 ["go", 120.0]
    left(120)                  ← ["left", 120.0]，120 度正是等边三角形的外角
    go(120px)
    left(120)
    go(120px)                  ← 缩进结束，"三角形" = 5 条指令存进 avg_def 语句
S.AVG-button(x:0, y:0, "box")  ← CALL_RE（连字符）+ parse_args（冒号）联合作业
```

运行时执行到 `avg_def`：五条指令登记进 `runtime.avg_shapes["三角形"]`，
不产事件。执行到 `avg_button`：坐标 `x:0,y:0` 走 kwargs，形状 `"box"` 是内置名，
产出事件 `{"t":"avg","action":"draw","shape":"box","x":0.0,"y":0.0}`；
而 `S.AVG-button(-260,-180,"三角形")` 产出的同款事件里会多一个 `"ops"` 字段
——五条指令整队出发。Session 把事件追加进 `scene["avg"]`；
下一帧 pygame 画出来：画面正中一个方框，左下角一个绿色三角形。

注意一个细节：`S.AVG-button` **不阻塞**。它是副作用事件，画完就过，
紧接着的台词立刻显示——所以「先画形状再说话」的演出可以自由组合。
如果想要「画一笔停一停」的逐帧动画感，就在两次 `AVG-button` 之间
放一句空旁白 `""`，靠玩家点击推进。

---

## 七、网页版架构（htmlpub.py + web_bridge.py + webplayer.html）

网页版发布一条命令：`python tools/htmlpub.py 项目目录`，产物是单目录静态站。

**三层结构**：

1. **htmlpub.py（发布器）**：解析剧本 → 把 AST、素材、引擎源码全部塞进
   webplayer.html 模板的占位符。`WEB_MODULES` 列表是生死簿：
   runtime.py 顶层 import 的每个模块都必须在列（现在包括 avg.py），
   少一个浏览器里整包 ImportError，打开一片空白还毫无报错。
2. **web_bridge.py（引擎桥）**：在 Pyodide 里跑**真正的 Runtime**。
   难点是浏览器没有同步 socket：R.api 抛 `_PendingAPI`（故意继承 BaseException
   躲开 run() 的异常兜底）→ 页面 fetch → `resolve_api` 进缓存 → 重建执行流重放接回。
   **定位挂起点用 api 序号，绝不用事件条数**——首轮和重放产出的事件数不一样。
   stm.os 则落到内存镜像 VirtualFS，remove 进虚拟回收站、revision 留 .bak，
   碰不到玩家真实磁盘。
3. **webplayer.html（播放器）**：JS 只管画面和输入。wasm 引擎加载失败时自动退回
   **内置 JS 解释器**（同一条事件流的降级实现）——表达式函数表 `FNS` 对齐
   `SAFE_BUILTINS`，AVG 的 `avg_def / avg_button / avg_clear` 三个分支也在
   `execStmt / doCall` 里对齐了。新加桌面白名单函数或新语句时，记得同步 JS 侧。

---

## 八、工具链（tools/）

| 工具 | 用途 |
|------|------|
| `check.py` | 逐行语法检查，五级错误分级，`--verbose` 能打印语句树 |
| `doctor.py` | 剧本体检：未初始化变量、未判断选项、缺失素材 |
| `selftest.py` | 引擎自测七连（其中启动器一项缺 CustomTkinter 会跳过） |
| `modcheck.py` | 美化包完整性检查 |
| `htmlpub.py` | 发布网页版（`--engine js` 全离线 / `--inline` 单文件） |
| `stmenc/` | 加密打包发布 |

**每次改完引擎必跑**（按顺序，全绿才算完）：

```bash
python tools/selftest.py
python tools/check.py demo --verbose
python start.py --auto demo/script.stm
python tools/doctor.py demo
python tools/modcheck.py
python stmenc/start.py demo --out <临时目录> --key test
python tools/htmlpub.py demo --out <临时目录> --no-assets
```

已知环境性失败：selftest 的「找到带错误的剧本」一项依赖 `projects/` 下的一个
不在仓库里的目录，失败属正常。AVG 相关的补充测试在 `_devtest/avg_smoketest.py`
（解析 + 无头推进 + 快照 + 几何比对，Python/JS 两版海龟输出已验证一致）。

---

## 九、二次开发指南：怎么给引擎加一个新能力

以 AVG 为样板，任何新功能都可以走这条流水线：

1. **定语法**：在 parser.py 顶部加正则，在 `_parse_lines` 里加分支，
   产出一条新的语句类型（AVG 的是 `avg_def`）。能解析期报错就别拖到运行时。
2. **定事件**：在 runtime.py 的事件类型表（文件头注释）里登记新事件，
   `exec_block` / `do_call` 加分支，产出纯 JSON 的事件字典。
3. **登记副作用**：事件不需要等玩家？必须加进 `session.SIDE_EFFECTS`，
   并在 `Session._apply` 里定义它怎么改 scene，在 `_scene_copy` /
   `_apply_snapshot` 里定义它怎么进快照。**漏掉这步的表现是读档卡死。**
4. **两端渲染**：render.py 写 pygame 绘制函数、gui.draw_scene 挂图层；
   webplayer.html 的 `apply()` 加 case，必要时在 JS 解释器里同步实现。
5. **体检与工具**：`_validate` 加静态检查（如「引用了没定义的形状」给 warn），
   `check.py` 若有资产类需求同步扩展。
6. **文档**：README 的特性清单、语法速查、「已知限制」三处都要过一遍——
   「已知限制」最容易过期，写之前先对照代码确认。
7. **验收**：跑第八节的七连，外加一个像 `_devtest/avg_smoketest.py` 一样的
   自测脚本留作证据。

**向后兼容是硬要求**：新能力一律「写了才生效，不写走原路径」。
老剧本、老存档、老 options.stm、老美化包都必须照常工作。

## 九点五、存档格式详解

一份 format 2 的存档长这样（字段都有注释，抄下来对照 save.py 读）：

```
format       固定为 2，引擎靠它分流新老存档
script       剧本路径
title        剧本标题（成就 / CG 回廊按标题区分）
answers      重放流水：[["choose", 选项索引], ["question", 输入],
             ["rand", 随机数], ["api", {结果记录}], ["os", {结果记录}]]
say_count    已经放完的台词数——重放的「停车点」
history_tail 最后三句台词（读档瞬间对话框不至于空白）
chosen       已经选过的选项集合（If "选项" 判断用）
vars         用户变量快照（只含 JSON 友好类型；STM / R 命名空间不进）
scene        画面快照：bg / picture / sprites / bgm / bgm_loop / avg
lang         该存档用的语言版本
```

理解两个字段就理解了整个存档系统：

**answers 为什么记索引不记文本？** 多语言剧本里同一处选择在中文版和日文版的
选项文字不同，记文本的话换语言读档就错位；记「第几个选项」则永远对得上。
老存档里记的是文本，`_take_answer` 对两种都兼容。

**为什么 scene 快照和重放要双轨并用？** 重放只能保证「执行位置对」，
但有些画面细节未必能由重放精确重建（比如立绘补间中途存的档）；
快照则相反——画面一定对，但执行位置无法表达。两者结合：
先重放对位置，再用快照覆盖画面，取长补短。

给 AVG 画图层做存档时用的正是这套现成机制：形状事件是副作用，
重放时被 `_apply` 重新应用一遍；快照里 scene.avg 又是最权威的图层清单。
新功能只要遵守「副作用事件 + 纯 JSON 快照」两个约定，存档就自动工作。

---

## 九点七、打包与发布流程

**本地试跑**：`python start.py 项目目录` 或双击 STMG启动器.bat。

**加密发布**：`python stmenc/start.py 项目目录 --out 输出目录 --key 口令`。
产物是一个独立目录（剧本变成 .stmdec），玩家双击 start.bat 就能玩；
想封单个 exe 再跑产物里的「打包成 exe」脚本（内部走 PyInstaller）。

**网页发布**：`python tools/htmlpub.py 项目目录`，常用参数：

```
--out 目录         产物位置（默认 dist/<项目名>_web）
--engine js        用页面内置解释器，完全离线、不打包 Pyodide（约 77KB vs 238KB）
--inline           素材转 base64 内联，整个游戏变一个 HTML 文件
--no-assets        不带素材（纯逻辑自测用）
--mod 美化包id     带指定美化包
--pyodide cdn|URL  指定 Pyodide 加载源（默认本地有就用本地）
```

发布器做完会自动给三条提醒：联网接口的跨域风险、stm.os 沙箱限制、
内联模式的体积膨胀。产物可以整个目录丢 GitHub Pages，双击 index.html 也能本地玩。

**多语言**：项目里放 `script.ja.stm`、`script.en.stm`，标题界面自动出现
「语言」按钮；玩家的选择存在存档目录，存档里也记着语言版本。

---

## 九点九、常见问题（FAQ）

**Q：改了引擎，玩家手里的老存档会坏吗？**
A：只要遵守「新能力写了才生效、scene 快照纯 JSON、副作用登记 SIDE_EFFECTS」
三条约定就不会。AVG 图层就是这么做的：老存档没有 avg 键，读进来是空图层，
一点不碍事。

**Q：为什么我的 S.xxx 函数在网页版没反应？**
A：三个可能：①只在 runtime.py 实现了，webplayer.html 的内置 JS 解释器没有同步
（`--engine js` 或 Pyodide 加载失败时会走到）；②htmlpub 的 WEB_MODULES 漏了
你新加的模块，浏览器里整个引擎 import 不起来；③函数名里有特殊字符没过
CALL_RE。先在桌面 `--auto` 跑一遍确认引擎侧没问题，再查网页侧。

**Q：怎么调试剧本？**
A：`python tools/check.py 剧本 --verbose` 看语句树和报错；
`python start.py --auto 剧本` 无头跑全流程（打印每条事件）；
`python tools/doctor.py 项目目录` 体检变量和素材。开发模式下游戏内
toast 会报运行时错误详情。

**Q：AVG 画的东西会挡住选项吗？**
A：图层顺序是 背景 → 叠图 → 立绘 → AVG → 对话框/选项。AVG 在选项底下，
不会挡交互；想给选项做装饰背景反而可以利用这一点。

**Q：海龟绘图的 left(90) 之后 go 是朝哪个方向？**
A：数学坐标、逆时针为正。初始朝右（3 点钟方向），`left(90)` 后朝上
（12 点钟方向），`right(90)` 朝下。y 轴向上，所以「left 转完往上走」，
画出来的形状和数学作业纸上的一致。

**Q：一个形状能多次定义吗？**
A：能。后面的 `SET 同名:` 覆盖前面的（runtime 的 avg_shapes 是普通字典），
但定义在分支里的只在分支执行到时生效——定义也是语句，按执行顺序算。

---

## 附录 A：每个模块「删了会怎么样」对照表

开发者的常见疑问是「这个文件能不能动」。逐个过一遍（理解了这个表，
就理解了模块间的依赖方向）：

**parser.py** —— 删了什么都别删它。所有语句类型、正则、错误分级都在这。
删掉任何一条正则，对应的语法立刻整批失效，而且报错信息会退化成
「这一行没看懂」。改它之前先跑 `tools/check.py demo --verbose` 留个基线输出。

**runtime.py** —— 事件流的源头。删掉 `do_call` 里的任何分支，
对应的 S 函数会落进兜底的「这个函数还没实现」toast，不崩但失效。
删掉 `SAFE_BUILTINS` 里的函数，剧本算式立刻「算不出来」；
记得同步网页版 JS 解释器的 FNS 表，否则两边行为不一致。

**session.py** —— 删掉 `_apply` 里的分支，画面就不会变了；
删掉 SIDE_EFFECTS 里的登记，推进直接卡死在那个事件上；
删掉快照里的字段，读档后对应状态回退到重放结果（或空白）。

**gui.py / render.py** —— 删了游戏就没画面，但 `--auto` 无头模式照常能跑
（这正是分层的好处）。gui 里的按钮、菜单、存读档界面互相独立，
改菜单不会影响推进逻辑。

**avg.py** —— 第 3 期的新核心。删掉它 parser 和 runtime 都 import 不起来，
整个引擎瘫掉；只删 `run_turtle` 则自定义形状画不出来（内置 box/circle
用的是 primitive_geometry，还能画）。它的文件头就是语法说明书，改规则先读头。

**web_bridge.py / webplayer.html** —— 只影响网页版，桌面无感。
但 webplayer 里有两份必须手动对齐的东西：JS 解释器（对齐 runtime 语义）
和 AVG 绘图翻译版（对齐 avg.py 语义）。

**audio.py / save.py / mod.py / uiconf.py** —— 各管一摊，
互相几乎不依赖。save.py 特殊一点：runtime 和 session 都 import 它
（成就、CG、快照），删了会连环崩。

**crypto.py / stmos.py / errors.py** —— 既有语义不要动（项目约定）。
errors 的 Issue 分级是 check 和游戏内错误界面共用的契约，
改级别名会同时影响两边的展示。

## 附录 B：AVG 进阶练习题

光读不练假把式。按顺序做完这些小练习，AVG 系统和引擎结构就都吃透了：

1. **画一个五角星**。提示：五角星是「前进两条边长、右转 144 度」重复五次，
   用 `Repeat 5:` 循环包住两行指令试试（Repeat 里面能不能放 SET 绘图块？
   动手试，然后想清楚为什么解析器允许或禁止）。
2. **给 AVG 加一个新指令 `home()`**：让笔回到原点、朝向归零、不断线。
   要改 avg.py 的 OP_SPEC 和 run_turtle，以及 webplayer.html 的 avgRunTurtle——
   正好练一遍「双端同步」。
3. **做一个打字进度条**：`If` 判断变量，配合 `SET` 循环用
   `S.AVG-button` 画一排小方块。体会「AVG 是副作用事件、不阻塞推进」的含义。
4. **给 AVG 形状加旋转参数 `rotate=`**：从 runtime（收参数）到 avg.py
   （几何变换）到两端渲染层都要动。做完这道题，你就可以独立往引擎里
   加完整的新功能了。
5. **想清楚一道思考题**：为什么 AVG 事件要设计成「事件自带 ops」，
   而不是渲染层回头查 runtime.avg_shapes？提示：网页版的渲染层
   （JS）有没有办法读到 Python 侧的字典？读档重放时呢？

做完练习 5，你对这个引擎「事件流贯通一切」的设计就真正有手感了。

## 附录 C：引擎调用与剧本语法全景速读

写剧本时能用什么、各自由哪个模块实现，一张表看完（详细参数见 README 语法手册）：

**结构语句**（parser.py 解析）：`Start:` 入口标签；`If 条件:` / `Else:` /
`EndIf` 分支；`Choose:` 加缩进的 `"选项"` 行做选择支；`Question:` 玩家输入；
`SET 变量 = 算式` 赋值（支持算式、字符串拼接、SAFE_BUILTINS 里的函数、
RAND 随机）；`SET 名字:` 定义 AVG 绘图变量（第 3 期）；`Repeat N:` /
`While 条件:` 循环；`Call "标签"` / `Return` 子程序；`include "文件"`
多文件拼接；`<python: ... >` 内嵌 Python（开发模式专属）。

**S 系演出调用**（runtime.do_call 的 S 分支）：`S.character` 登记角色或放立绘
（pos / tag / scale / alpha / y / rotate / expr / dur 全套增强参数）；
`S.cg / S.bg / S.picture` 背景与叠图（换背景自动清立绘）；`S.play / S.sound /
S.voice` 三通道音频；`S.stop / S.hide` 停音频、藏图层；`S.transition` 转场
（fade / dissolve / flash）；`S.jump / S.end` 跳转与结束；`S.AVG-button /
S.AVG-clear` AVG 绘图（第 3 期）。

**STM / R 系统**：`STM.Q / STM.ANSWER` 输入提示与结果；`STM.display` 右上角
提示；`stmg.python` 声明白名单库；`STM.achieve` 解锁成就；`R.api` 联网
（key=option 走 options.stm 配置）；`stm.os(...)` 受控文件操作。

**头部设置**（第一块 `名称=值`）：`Size` 分辨率、`Title` 标题、`Font` 字体、
`Ver` 版本号、`Lang` 默认语言。

### 开发约定清单（改引擎前最后读一遍）

1. **向后兼容是硬要求**。老剧本、老存档、老 options.stm、老 custom/gui.py、
   老美化包都要照常工作。判断标准：把仓库退回上一个版本生成的产物拿来跑，
   一切照旧才算及格。
2. **存档必须纯 JSON**（`ensure_ascii=False`），不许 pickle，
   快照里跳过不可序列化的对象。
3. **副作用事件必须登记 `session.SIDE_EFFECTS`**，否则推进卡死——
   每次加新事件都默念一遍。
4. **`include` 是解析期内联**，公共段落写在主流程走不到的末尾配 `S.end()`。
5. **中文注释、中文报错文案**，语气对齐现有代码；注释要回答三个问题：
   这段代码干什么、删了会怎么样、参数是什么——AVG 相关代码就是按这个标准写的，
   照着那个密度来。
6. **不动 crypto.py / errors.py / markdown.py / stmos.py 的既有语义**。
7. **改 gui.py / launcher.py 这类大文件时精准定位**，不顺手重构无关代码。
8. **`.workbuddy/` 与 `_devtest/` 不进仓库**；自测脚本放 `_devtest/`
   留作交付证据；改完先本地过七连验收，再谈提交。
9. **新增功能同步更新 README** 三处：特性清单、语法速查表、「已知限制」
   （最容易过期的一章，写之前先对照代码确认）。
10. **双端对齐**：动了 SAFE_BUILTINS、新语句类型、AVG 规则，都要检查
    webplayer.html 的 JS 解释器 / 翻译版是否需要同步。

---

## 十、设计哲学小结

- **一条事件流贯通一切**：解析 → 运行 → 推进 → 渲染，层与层之间只传 JSON 字典，
  所以才能「同一份代码」跑在桌面、WebAssembly、无头测试三个环境里。
- **宽容优先**：缺素材画占位、坐标算错画正中、没定义的形状静默跳过——
  引擎不崩是底线，报错（带行号、带建议）是开发期的礼物。
- **回放即存档**：把「玩家的选择」和「世界的随机」都记成流水，
  任何时候都能从开头精确重放回某一拍。这个机制撑起了存档、读档、
  网页断线重连（R.api 重放）三套功能。
- **双端对齐靠纪律**：JS 翻译版必须在改 Python 侧时同步维护，
  所有两端都可能出现的文件头都有醒目警告注释。

祝开发顺利。改完记得跑验收，然后让杂鱼……让作者亲自玩一遍喵。

*（本教程对应引擎版本：第 3 期，含 AVG 绘图系统。全文约一万字。）*
