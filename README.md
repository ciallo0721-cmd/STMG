# STMG

**Super Text Markdown Galgame** —— 用 Markdown 风格的语法写视觉小说。

[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![pygame](https://img.shields.io/badge/dependency-pygame-green)](https://www.pygame.org/)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

写起来大概长这样：

```stm
<
Size=1280x720
title="我的第一个游戏"
Font="Microsoft YaHei"
>
<
Start:
S.character("角色1")
S.cg("bg/room.png")
S.play("music/bgm.mp3")

"桌上放着一张纸条。"
角色1"你好，世界。"

SET 好感度 = 0

Choose:
    "读纸条":"先睡一觉"

If "读纸条":
    S.picture("png/note.png")
    "纸条上写着：**今天之内要搞定这个引擎**。"
    SET 好感度 = 好感度 + 10

STM.Q = "请给自己取个名字："
Question:

"你好，[color=#ff88bb]**" + STM.ANSWER + "**[/color]。"
>
<
"感谢游玩"
>
```

缩进就是分支，`**粗体**` 直接写在台词里，选择支和条件判断各占一行。

头部那个 `< >` 是可选的：整份剧本只写一个 `< >` 把剧情全包进去也能跑
（引擎靠「有没有标签行」分辨头和正文，头部里只有 `名称=值`，不会撞车）。
`Start:` 不分大小写，写成 `start:` 一样认。

---

## 目录

- [特性](#特性)
- [快速开始](#快速开始)
- [语法速查](#语法速查)
- [完整语法手册](#完整语法手册)
- [游戏内错误界面](#游戏内错误界面解析错误不进命令行)
- [项目结构](#项目结构)
- [命令行工具](#命令行工具)
- [自定义界面与引擎](#自定义界面与引擎)
- [美化包（mod）](#美化包mod换主题)
- [打包发布](#打包发布)
- [关于加密](#关于加密重要)
- [已知限制](#已知限制)
- [常见问题](#常见问题)
- [许可](#许可)

---

## 特性

- **Markdown 风味语法** —— 缩进即分支，注释、内联标记都按 Markdown 的习惯来，写剧本像写笔记
- **剧本与引擎分离** —— 引擎代码是干净的 Python 包，改剧本不需要碰它
- **多立绘 + 站位** —— 可以同时站好几张立绘，用 `pos=` 和 `tag=` 控制位置和身份
- **三通道音频** —— BGM / 音效 / 语音各自独立音量，音效不会打断 BGM
- **md 内联渲染** —— 加粗、斜体、删除线、颜色、字号、注音，文本框里直接生效
- **完整 galgame 体验件** —— 存档读档、历史回顾、自动播放、快进、打字机、设置界面
- **剧本里能嵌 Python** —— `<python: ... >` 跑一段代码，`print` 的内容逐行飘到右上角
- **带语法检查器** —— `--check` 逐行报错，五级错误分级，写错了不用开着窗口试
- **加密发布** —— 一键把剧本和素材打包成 `.stmdec`，纯标准库实现，零额外依赖
- **缺素材不崩** —— 图还没画好也能跑，引擎会自动画占位块
- **图形化启动器** —— 项目管理、新建模板、检查、试跑、打包、发布，点点鼠标就行
- **发布成网页** —— 一键生成能直接玩、能分享的 HTML，逻辑跑的是**真引擎**（WebAssembly，不是重写一遍）
- **能转 Ren'Py** —— 剧本可以反向导出成 `.rpy`，想换引擎不用重写
- **界面可自定义** —— 项目里的 `custom/gui.py` 随便改：对话框位置、名字框颜色、标题图、标题曲
- **能换主题** —— `mod/` 下放美化包（`gui.py` + `theme.css` + `theme.js`），换个外观不改引擎，还能单独打包成「美化包」分享

第 2 期补齐的一批（下面都有详细说明）：

- **多文件剧本** —— `include "chapter1.stm"` 把正文拆成多个文件，长剧本不用全挤在一个文件里
- **子程序与循环** —— `Call "标签"` / `Return` 写可复用的公共段落，`Repeat N:` / `While 条件:` 让重复演出不用复制粘贴
- **补间动画** —— `S.character("x.png", pos="left", dur=0.4)`：立绘和背景的移动、淡入带过渡，不再是瞬切
- **语音自动挂载** —— `options.stm` 里开 `AutoVoice`，配音按 `voice/<角色>/<序号>.wav` 自动找，剧本里不用一句一条路径
- **状态快照存档** —— 存的是完整游戏状态（变量 / 场景 / 已选），读档不再从头重跑，`RAND()` 与联网结果也不会错位
- **存档导入导出** —— 存档能导出成 `.stmgsav` 单文件，换电脑、发给朋友都能用
- **快速存读 + 存档缩略图** —— `F5` / `F9` 直接存读上次用的槽，存档界面有画面缩略图认档
- **设置面板扩充** —— 游戏里能调字号、行距、对话框透明度、打字机开关、界面字体
- **音频增强** —— BGM 淡入淡出、顺序播放列表，flac 尽力支持
- **剧本一键体检** —— `tools/doctor.py` 出健康度报告（结构统计 / 孤儿标签 / 未用素材 / 可疑项）
- **增量更新** —— `tools/patch.py` 只发改动过的资源，玩家不用重下整个包

---

## 快速开始

需要 Python 3.8 或更高版本。

```bash
git clone https://github.com/ciallo0721-cmd/STMG.git
cd STMG
python -m venv .venv
```

Windows：

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
STMG启动器.bat
```

macOS / Linux：

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python launcher.py
```

Linux 上如果提示缺 `tkinter`，装一下：`sudo apt install python3-tk`。

### 用启动器

左边是项目列表，右边是操作按钮：

| 按钮 | 作用 |
|---|---|
| 启动游戏 | 开窗口跑当前项目 |
| 语法检查 | 逐行检查剧本，输出打在下面的日志区 |
| 无头试跑 | 不开窗口，自动选第一个选项跑一遍，打印全部台词 |
| 打包发布 | 生成加密的发布版到 `dist/` |
| 发布为 HTML | 生成能直接玩 / 能分享的网页版到 `dist/<项目名>_web/` |
| 转为 Ren'Py | 把剧本导出成 `.rpy` 到 `dist/<项目名>_renpy/` |
| 编辑剧本 | 用系统默认编辑器打开 `script.stm` |
| 打开文件夹 | 打开项目目录 |

第一次用点「**新建项目**」，会生成一份能直接跑的模板（自带变量、选择支、询问输入的示例），
另外还会给你 `custom/gui.py`（改界面）和 `custom/markdown.py`（加自己的内联标记）。

> 启动器界面用的是 CustomTkinter，第一次跑 `pip install -r requirements.txt` 就会一起装上。
> 没装的话启动器会告诉你装在哪，`STMG启动器.bat` 也会自动帮你装。
> 引擎本身不需要它——启动器开不开得了，跟游戏能不能跑没关系。

> 「移除项目」不会删文件，只会把整个文件夹挪到 `projects/_trash/`，随时可以拖回来。

### 不用启动器

```bat
start.bat                           :: 无参数 = 打开启动器
start.bat demo\script.stm           :: 直接跑指定剧本
start.bat projects\我的游戏\script.stm

:: 或者直接用 Python
.venv\Scripts\python.exe start.py demo\script.stm
.venv\Scripts\python.exe start.py --check demo\script.stm    :: 只检查语法
.venv\Scripts\python.exe start.py --auto  demo\script.stm    :: 无头跑一遍
.venv\Scripts\python.exe start.py --auto=1 demo\script.stm   :: 自动选第二个选项
.venv\Scripts\python.exe start.py demo\script.stm --mod example_sakura
.venv\Scripts\python.exe start.py demo\script.stm --no-mod   :: 这次不用美化包
```

### 操作

| 操作 | 按键 |
|---|---|
| 推进 | 鼠标左键 / `空格` / `回车` |
| 历史记录 | 滚轮上翻 / `H` |
| 自动播放 | `A` |
| 快进 | 按住 `Ctrl` |
| 存档 / 读档 | `F5` / `F9`（直接存 / 读上次用的那个槽） |
| 存读档界面 | `Shift`+`F5` / `Shift`+`F9` |
| 全屏 | `F11` |
| 菜单（音量、文字速度、存读档） | `Esc` |

> `demo/` 是故意不放素材的示例，跑来跑去都是占位块——那是正常的，不是 bug。

---

## 语法速查

| 写法 | 意思 |
|---|---|
| `"台词"` | 旁白（不显示名字框） |
| `角色1"台词"` / `角色1: "台词"` | 让「角色1」说话 |
| `<-- 注释 -->` | 注释 |
| `S.character("角色1")` | 注册角色 |
| `S.character("png/立绘.png")` | 显示立绘 |
| `S.character("png/立绘.png", pos="left", tag="角色1")` | 显示立绘并指定站位和身份 |
| `S.hide("角色1")` | 让指定立绘退场 |
| `S.cg("bg/教室.png")` | 换背景（会清空所有立绘） |
| `S.picture("png/纸条.png")` | 背景之上叠一张图 |
| `S.play("music/bgm.mp3")` | 播放 BGM（默认循环） |
| `S.sound("music/开门.wav")` | 播放音效 |
| `S.voice("music/v001.wav")` | 播放语音 |
| `S.stop("bgm")` / `S.stop("all")` | 停音频 |
| `S.hide("sprite")` / `S.hide("all")` | 清空立绘 / 清空所有图层 |
| `S.jump("标签名")` / `S.end()` | 跳转 / 直接结束 |
| `SET 变量 = 值` | 赋值 |
| `STM.display("文字")` | 右上角弹一条提示 |
| `stmg.python("math")` | 声明 python 代码块能用的库（`"none"` = 不用库） |
| `<python: 代码 >` | 内嵌一段 Python，`print` 的内容逐行飘到右上角（开发模式专属） |
| `R.api(url="...", key=option)` | 发 HTTP 请求，结果在 `STM.API` |
| `stm.os(read("C:/a.txt"))` | 读文件，内容进 `STM.OS`（静默，不弹提示） |
| `stm.os(create("C:/a.txt"))` | 建空文件（已存在则不动） |
| `stm.os(remove("C:/a.txt"))` | 删文件（移回收站，不是永久删） |
| `stm.os(revision("C:/a.txt"),"旧"to"新")` | 改文件，先留 `a.txt.bak` 备份 |
| `include "chapter1.stm"` | 把另一个剧本文件的正文内联进来 |
| `Call "公共段落"` / `Return` | 调用子程序 / 从子程序返回 |
| `Repeat 3:` / `While 好感度 < 100:` | 循环，循环体缩进 4 格 |
| `S.cg("bg/x.png", dur=0.6)` | 换背景，带 0.6 秒过渡 |
| `S.character("png/x.png", pos="left", dur=0.4)` | 立绘带过渡移到左边 |

---

## 完整语法手册

### 文件骨架

一个 `.stm` 文件由三个 `< ... >` 块组成，靠**顺序**区分：

```stm
<
Size=1280x720
title="我的第一个游戏"
Ver="1.0.0"
Pack="com.example.example"
Lang="cn"
Font="Microsoft YaHei"
>
<
Start:
...正文...
>
<
"感谢游玩"
>
```

| 字段 | 说明 |
|---|---|
| `Size` | 基准分辨率（`Large=` 也认，兼容旧写法） |
| `title` | 窗口标题，也是标题界面的默认大标题 |
| `Ver` | 版本号，显示在标题界面 |
| `Pack` | 包名，目前保留不用（留给以后上手机） |
| `Lang` | 语言标记，目前保留 |
| `Font` | 首选字体名，找不到会自动回退到系统里的中文字体 |

第 1 块是头，第 2 块是正文，第 3 块（可省略）是结局画面。

### 台词

```stm
"这是旁白，不显示名字框。"

角色1"这是角色1说的话。"
角色1: "冒号写法也行。"
```

带 `+` 号或 `STM.` 的台词会被当成表达式求值，其余一律当纯文本：

```stm
"你好，**" + STM.ANSWER + "**。"
"价格是 100 + 50 元"      <-- 这是纯文本，不会算成 150
```

### 选择支与条件

```stm
Choose:
    "去图书馆":"回宿舍"

If "去图书馆":
    S.cg("bg/图书馆.png")
    "图书馆很安静。"

If "回宿舍":
    S.cg("bg/宿舍.png")

Else:
    "哪儿也不去。"

EndIf
```

- **缩进 4 格（或 Tab）就是进入上一层分支** —— 这和 Markdown 的精神一致
- `EndIf` / `EndChoose` 可写可不写
- `If "选项名"` 判断「有没有选过这个选项」
- `If 好感度 >= 10` 判断变量
- 没有 `Elif`，用 `Else:` 里面套 `If` 即可

### 询问玩家输入

```stm
STM.Q = "请问你叫什么名字？"
Question:

"原来叫 **" + STM.ANSWER + "** 啊。"
```

- 提示文字写在 `STM.Q` 里，也可以缩进写在 `Question:` 下面
- 玩家输入的结果存在 **`STM.ANSWER`**

### Markdown 内联

台词里可以直接写：

| 写法 | 效果 |
|---|---|
| `**粗体**` | 加粗 |
| `*斜体*` | 斜体 |
| `~~删除线~~` | 删除线 |
| `` `等宽` `` | 等宽（带浅灰底） |
| `[color=#ff88bb]文字[/color]` | 文字颜色 |
| `[size=28]文字[/size]` | 字号 |
| `{ruby:汉字|かんじ}` | 注音，渲染成「汉字(かんじ)」 |

### 变量

```
SET 好感度 = 0
SET 好感度 = 好感度 + 10
SET 姓名 = STM.ANSWER
SET 心情 = "开心"
```

变量名可以是中文。第一次出现必须用 `SET`，之后直接写名字引用。

### options.stm

```stm
<
About = "显示在「关于」界面里的文字"
Enc   = "加密口令"
dec   = "*.stm,*.png,*.jpg,*.mp3,*.wav,*.ogg"
AllowNet = "true"
>
```

| 字段 | 说明 |
|---|---|
| `About` | 「关于」界面的内容 |
| `Enc` | 加密/解密口令，打包时用 |
| `dec` | 打包时收集哪些文件（逗号分隔的 glob） |
| `AllowNet` | 发布版要不要允许 `R.api` 联网，默认 `true` |

`R.api(key=option)` 会从这里的 `Enc` 取值，剧本里就不用写明文密钥。

### 补充约定

设计稿没写死、但实现必须拍板的地方：

| # | 项目 | 约定 | 原因 |
|---|---|---|---|
| 1 | 玩家输入存哪 | `STM.ANSWER` | 只规定了提示文字 `STM.Q`，没说输入存哪 |
| 2 | `If` 的范围 | 缩进 4 格，`EndIf` 兼容 | 没有结束标记，解析器必须有个判定依据 |
| 3 | 台词求值 | 带 `+` 或 `STM.` 才算表达式 | 否则每句台词都要考虑转义 |
| 4 | 引号 | 全角 `“ ”` 自动纠正成半角 | 中文输入法下很容易打错，直接容错 |
| 5 | 立绘身份 | `tag=` 默认用图片文件名 | 同框多张立绘需要区分 |
| 6 | `S.cg()` | 换背景会清空立绘 | 和 Ren'Py 的 `scene` 语义一致 |

---

## 多文件剧本（include）

长剧本不要全挤在一个 `script.stm` 里，用 `include` 拆开：

```stm
<
Start:
"第一章开始。"
include "chapter1.stm"
"第一章结束。"
S.end()

<-- 公共段落要写在主流程走不到的地方（S.end() 之后）-->
include "common.stm"
>
```

- 路径**相对当前剧本文件所在目录**解析；找不到会在游戏内的错误界面里报出来
- 禁止循环包含（A include B、B 又 include A 会直接报错，不会死循环）
- ⚠️ **include 是「解析期正文内联」**：被包含文件里的句子会按顺序落在主流程上，
  所以公共段落 / 子程序段落必须写在主流程走不到的末尾，否则会被顺路执行
- 报错带文件名，形如 `chapter1.stm:行12`

## 子程序与循环（Call / Return / Repeat / While）

```stm
<
Start:
SET 好感度 = 0
Call "打招呼"
"打过招呼了。"

Repeat 3:
    "这段重复三遍。"

While 好感度 < 30:
    SET 好感度 = 好感度 + 10

打招呼:
S.character("png/菲.png", pos="center")
"你好呀。"
Return
>
```

- `Call "标签"`（写 `Call 标签` 也行）跳到标签，段尾的 `Return` 回到 `Call` 的下一句
- `Return` 在**调用栈为空**时 = 直接结束剧本 —— 所以子程序段落务必放在主流程走不到的末尾
- `Repeat N:` 的 N 可以是表达式（`Repeat 次数:`）；`While 条件:` 每一轮重新求值
- `While` 有 **10000 次硬上限**，写成死循环会被引擎拦下并报错，不会卡死窗口
- 循环体必须缩进 4 格（和 `If` / `Choose` 一个规矩）

## 补间：给演出加 `dur`

```stm
S.cg("bg/教室.png", dur=0.6)
S.character("png/菲.png", pos="left", dur=0.4)
S.character("png/菲.png", pos="right", alpha=120, scale=1.2, rotate=3)
```

`sprite` / `bg` / `picture` 都认 `dur=`（秒）。不写 `dur` 就是瞬切 —— 老剧本行为完全不变。
快进和「跳过已读」生效时动画会直接落到终态，不拖慢快进。

## 语音自动挂载（AutoVoice）

不想一句一条 `S.voice("...")`，就在 `options.stm` 里开开关：

```stm
<
AutoVoice = "true"
VoiceDir  = "voice"      <-- 可选，默认就是 voice
>
```

之后**有角色名**的台词会按顺序找下面两个路径，找到就播、找不到就静默跳过（缺配音是常态）：

```
voice/<角色名>/<该角色第几句，4位补零>.wav     <-- 先试这个
voice/<角色名>/<全局台词序号，4位补零>.wav     <-- 再试这个
```

三种格式都认：`.wav` / `.ogg` / `.mp3`。想给某一句手写语音照旧用 `S.voice("...")`。
读档重放时不会把配音再放一遍。

## 存档

- 存档是**状态快照**：变量、已选过的选项、当前画面（背景 / 立绘 / BGM）、翻到第几句，全都存
- 读档先用快照把画面还原，再把剧情推进到同一个断点；`RAND()`、`R.api`、`stm.os` 的结果
  也记在存档里，读档后走向与存档时**完全一致**
- 第 2 期之前的老存档照样能读（没有快照信息，仍走重放逻辑）
- 存读档界面可以「导出存档」成 `.stmgsav` 单文件，也能从文件「导入存档」
- `F5` / `F9` = 快速存读（上次用的那个槽）；`Shift`+`F5` / `Shift`+`F9` = 开存读档界面

---

## stm.os —— 受控文件操作（DDLC 式彩蛋用）

> 想做「游戏突然叫出你真实名字 / 偷偷改你电脑上某个文件」这种 DDLC 式演出？
> **别用 `STM.python`** —— 它是**开发模式专属**、会弹 toast，发布版里直接被禁用，
> 玩家只要翻一下启动器 / exe 就「穿帮」了。改用 `stm.os(...)`：它看起来就只是一个
> 普通游戏功能，发布版照常运行、**静默执行、不弹任何提示**，所以才藏得住。

`stm.os` 只暴露 4 个动作，而且每个都带安全兜底：

| 写法 | 作用 | 安全兜底 |
|---|---|---|
| `stm.os(read("C:/example.example"))` | 读文件，内容放进 `STM.OS` | — |
| `stm.os(create("C:/example.example"))` | 建一个空文件 | 已存在则不动 |
| `stm.os(remove("C:/example.example"))` | 删文件 | **移进回收站**，不是永久删除，能找回 |
| `stm.os(revision("C:/example.example"),"内容"to"内容2")` | 把文件里的「内容」改成「内容2」 | 改之前先留 `example.example.bak` 备份 |

读出来的内容用 `STM.OS` 取，直接在台词里拼：

```stm
stm.os(read("C:/path/to/name.txt"))
"……你叫 **" + STM.OS + "** 吧？我早就知道了喵。"
```

`revision` 的替换规则：

- `stm.os(revision("a.txt"),"旧文字"to"新文字")` 把文件里**所有**「旧文字」换成「新文字」
- 想直接**写入 / 覆盖**整份内容，可以把旧串传空：`stm.os(revision("a.txt"),""to"你要写的话")`
- 改之前一定先复制一份 `a.txt.bak`，改坏了把 `.bak` 改名回去即可

想看实际效果，直接跑 `demo/stmos_demo.stm` 就行（启动器里选它，或 `start.bat demo\stmos_demo.stm`）。

### 网页版里的 `stm.os`

发布成 HTML 之后，`stm.os` 一样能用，但「磁盘」换成了浏览器自己的 IndexedDB 沙箱：

- 剧本里写 `C:/Users/xxx/name.txt` 也好、写 `stmg-virtual://notes/a.txt` 也好，
  都只是沙箱里的一个键 —— **碰不到玩家真实的磁盘**，这是硬保证；
- 四个动作的语义和桌面版对齐：`remove` 进虚拟回收站 `.trash/`，`revision` 先留 `.bak`；
- 沙箱跟着站点数据走：换个浏览器、清空站点数据就没了；
- 浏览器不支持 IndexedDB、或者用户拒绝了存储时，退回「跳过 + 提示」，**不报错、不卡剧情**。

> 想让网页版的「叫出真实名字」有点诚意，可以让剧本在桌面版读真文件、在网页版读沙箱 —— 
> 同一份剧本，两边都跑得通。

> ⚠️ **伦理与合规**：这种能力本质是读写玩家机器上的文件。请只用于
> **自己电脑上的演示**，或**玩家明确知情同意**的演出（比如读写游戏**自己**的存档目录）。
> 拿它去偷窥、破坏别人文件既违法又不道德——那种情况被抓到是真的会穿帮的。

---

## python 代码块 —— 剧本里跑段代码（开发模式专属）

写剧本时想算点东西、或者打点调试信息，可以直接嵌一段 Python：

```stm
<
Start:
"example"
stmg.python("math")   <-- 这个块要用哪些库；不需要库就写 stmg.python("none")
<
python: 1             <-- 冒号后面的数字 = 每行 print 之间隔几秒（不写就是 3 秒）
print("1")
print("2")
total = sum(range(1, 11))
print("1 加到 10 是 %d" % total)
>"算出来的 total 能直接用在台词里：" + str(total)
>
```

跑起来是这样的：`1` 先出现在**右上角**，1 秒后 `2`，再 1 秒后最后一行；
提示飘完，剧情接着往下走（等的时候点一下可以直接跳过）。

| 写法 | 意思 |
|---|---|
| `stmg.python("math")` | 声明代码块能用的库，多个可以用逗号：`stmg.python("math,random")` |
| `stmg.python("none")` | 明确表示不需要额外库（这两行其实也可以全省略） |
| `<` 换行 `python:` | 代码块开口；开口和关键词分两行写也认 |
| `<python: 2` | 开口和关键词写成一行，冒号后面是每行之间的秒数 |
| 单独一行 `>` | 收尾 |

- 声明过的库直接按名字用（`math.sqrt(2)`），也能在块里 `import math`；
  但只有**白名单**里的库放得进来，名单和 `STM.python` 是同一份
  （`math / random / time / datetime / json / re / itertools / collections ...`）
- 代码里算出来的变量**自动带回剧本**，后面 `"..." + str(total)` 直接引用，不用再 `SET`
- 块里语法出错会停在游戏内的错误界面，并告诉你出错的是**剧本第几行**
- 一次最多飘 30 行，多出来的会提示「还有 N 行没有显示出来」
- 间隔只加在**行与行之间**：最后一行显示完就往下走；想让它多停一会儿，
  就在块后面写一句台词（台词本来就等玩家点）

> ⚠️ **开发模式专属**。立场和 `STM.python` 完全一致：发布版会**整块跳过**，
> 并在右上角说明一句。所以**别让剧情逻辑依赖它算出来的变量**——
> 面向玩家的正式功能请用 `SET` / `S.*` / `stm.os`。
> 想知道为什么：剧本里的代码是直接 `exec` 的，放进玩家机器上跑没有任何好处，只有风险。

网页版：默认的 WebAssembly 引擎跑的就是这份 Python 代码，代码块照常工作；
只有退回「页面内置解释器」时才跳过并提示。

想看实际效果，跑 `demo/script.stm` 最后那段就行。

---

## 游戏内错误界面（解析错误不进命令行）

剧本有语法错误时，引擎**不会**在命令行里刷一堆报错再退出，而是**照常开游戏窗口**，在游戏里显示一张错误界面（和 Ren'Py 的 `An error has occurred.` 一个意思）：

- 标题 `An error has occurred.`，下面列出全部错误，每条带 **行号 / 错误级别 / 原因 / 修复建议**；
- 开发模式（`dev_mode=True`，启动器默认就是）连「建议」一起显示；发布模式只给一句「联系作者」的温和提示；
- 错误太多一屏装不下？**滚轮翻看**；按 **回车 / Esc** 或点「退出」关掉窗口。

所以开发流程变成：**写剧本 → 直接开游戏看效果 → 报错就停在游戏里的错误界面，照着行号改 → 再开**。想在我不打开窗口的情况下批量过一遍语法，仍然用 `python start.py --check 剧本`（或启动器里的「语法检查」），那是专门的命令行检查器，照旧把结果打在日志区。

> 历史说明：旧版是「剧本有 N 个错误，先修好再开窗口」直接退出。现在改成进游戏内错误界面，体验更接近 Ren'Py，也更不容易被玩家/测试以为是引擎崩了。

---

## 项目结构

```
STMG/
├── launcher.py              图形化启动器（CustomTkinter）
├── STMG启动器.bat           双击打开启动器（缺依赖会自动装）
├── start.py                 剧本启动器：跑一个 script.stm
├── start.bat                Windows 快捷入口
├── stmg/                    ★ 引擎核心
│   ├── parser.py            .stm → 语句树
│   ├── runtime.py           语句树 → 事件流
│   ├── session.py           推进器：当前显示什么 / 存读档
│   ├── gui.py               pygame 主界面（外观由 uiconf 驱动）
│   ├── uiconf.py            界面配置：默认值 + 美化包 + 项目里的 custom/gui.py
│   ├── mod.py               美化包：加载、清单、**静态校验**（只改外观，不碰引擎）
│   ├── render.py            排版、文本框、立绘布局
│   ├── audio.py             BGM / 音效 / 语音
│   ├── markdown.py          内联标记 → 样式片段
│   ├── web_bridge.py        网页版桥：在 Pyodide 里跑这个真引擎
│   ├── webplayer.html       网页播放器模板（发布 HTML 用它渲染）
│   ├── pyodide/             WebAssembly 版 CPython 本体（tools/get_pyodide.py 下的，约 13MB）
│   ├── templates/           新建项目时拷过去的自定义文件
│   │   ├── custom_gui.py        界面配置模板
│   │   ├── custom_markdown.py   自定义标记模板
│   │   └── mod_*.py/css/js      美化包骨架模板（tools/modcheck.py --new 用它）
│   ├── options.py           options.stm 解析
│   ├── save.py              存档槽
│   ├── crypto.py            .stmdec 加解密
│   ├── pack.py              发布版资源容器
│   ├── project.py           项目的发现 / 新建 / 移除
│   ├── stdlib_api.py        STM.python 白名单 + R.api
│   ├── stmos.py             stm.os 受控文件操作（读/建/移回收站/改+备份）
│   └── errors.py            错误分级
├── stmenc/start.py          加密打包器
├── tools/
│   ├── check.py             语法检查器
│   ├── selftest.py          引擎自检
│   ├── doctor.py            剧本健康度报告（只读，结构 / 孤儿标签 / 未用素材 / 评分）
│   ├── renpy2stm.py         Ren'Py 工程 → STMG
│   ├── stm2renpy.py         STMG → Ren'Py（反向）
│   ├── htmlpub.py           STMG → 网页版（HTML）
│   ├── patch.py             增量更新：对比两版只输出改动过的资源
│   ├── modcheck.py          美化包静态检查（三条硬性限制）
│   ├── modpub.py            美化包发布：产出「XXX_美化包」（不含引擎本体）
│   └── get_pyodide.py       把 Pyodide 拉到本地，网页版就能离线跑真引擎
├── mod/                     ★ 美化包（外观主题）：none / example_sakura / 你自己的
├── demo/                    示例游戏（故意没有素材）
└── projects/                你自己的项目放这里
```

引擎本身不依赖 UI，`Runtime` + `Session` 可以完全无头跑，方便做自动化测试。

---

## 命令行工具

```bash
# 语法检查（带语句树）
python tools/check.py demo
python tools/check.py demo --verbose

# 引擎自检：解析 / 推进 / 加解密 / 资源包 / 界面 / 项目管理
python tools/selftest.py

# 剧本健康度报告（只读，绝不改剧本）
python tools/doctor.py demo
python tools/doctor.py projects/我的游戏 --out 剧本报告.md
python tools/doctor.py demo --json
```

自检覆盖 80 多项，改完引擎先跑它比开窗口快得多。

`doctor.py` 会给出一份体检：台词 / 角色 / 平均句长统计、`Choose` 与 `If` 结构、
孤儿 `label`（没人 `jump` 的）、被引用与**没被引用**的素材、可疑项（变量没 `SET` 就被判断、
选项没被判断过），最后是一个 0~100 的健康度评分。剧本里的路径如果是由变量拼出来的，
它只会算作「动态路径」，不会误报缺失。

### 美化包工具

```bash
python tools/modcheck.py                   # 列出美化包 / 当前启用哪个
python tools/modcheck.py example_sakura    # 详细检查一个包
python tools/modcheck.py --use example_sakura   # 启用
python tools/modcheck.py --new 我的主题     # 生成骨架

python tools/modpub.py example_sakura      # 校验通过后打包成「樱花飘落_美化包」
```

美化包只改外观、不碰引擎，检查项见 [美化包（mod/）](#美化包mod换主题)。

### Ren'Py 转换器

把现成的 Ren'Py 工程转成 STMG：

```bash
python tools/renpy2stm.py D:\renpy\你的工程\game
python tools/renpy2stm.py <游戏目录> --out projects/我的游戏 --title 游戏名
python tools/renpy2stm.py <游戏目录> --no-assets     # 只转剧本，不拷素材
```

`<游戏目录>` 指 Ren'Py 工程里的 `game` 文件夹（有 `script.rpy` 的那个）。

会做的事：

- `define x = Character("名字")` → 注册角色，并自动在开头补上声明
- `scene` / `show` / `hide` → `S.cg()` / `S.character(..., pos=, tag=)` / `S.hide()`，
  `at left` / `at right` 会转成站位
- `menu:` → `Choose:` + 每个选项一个 `If "选项":`
- `if / elif / else` → `If / Else`（`elif` 展开成 `Else:` 里套 `If`）
- `$ 变量 = 值` → `SET`，`renpy.input()` → `Question:` + `STM.ANSWER`
- `play music / sound`、`voice`、`stop music`、`jump`、`return` 全部对应转换
- `{b}` `{i}` `{color=}` `{size=}` 和 `[变量]` 插值 → Markdown 标记和字符串拼接
- `images/` 和 `audio/` 自动拷进新项目，资源名不写扩展名也能找到

转完会生成一份 `转换报告.md`，列出转换统计和所有需要手工处理的地方。
`screen` / `transform` / `style` 这类界面定义不会转（STMG 的界面在 `gui.py`），
转场（`with fade`）目前会丢弃。

---

## 打包发布

```bash
python stmenc/start.py demo
python stmenc/start.py demo --out dist/我的游戏 --key 我的口令
python stmenc/start.py demo --no-assets      # 只加密剧本，不打包素材
python stmenc/start.py demo --no-mod         # 不带上当前启用的美化包
```

产出：

```
dist/我的游戏/
├── script.stmdec      加密的主剧本
├── options.stmdec     加密的配置
├── assets.stmdec      素材打成一个加密资源包
├── stmg/              引擎本体
├── mod/               （若启用了美化包）外观主题，可删
├── start.py           生成的启动器（口令写在里面）
├── start.bat          双击运行
└── 打包成exe.bat      用 PyInstaller 封成单文件 exe
```

启用了美化包时，当前那份会一起拷进发布版的 `mod/`，玩家看到的就是你的主题；
不想要就加 `--no-mod`。注意发布版里带的**只是美化包**（样式），引擎依旧是
`stmg/` 里那份，两者是分开的。

封 exe 需要先装 PyInstaller：

```bash
pip install pyinstaller
```

然后双击发布目录里的「打包成exe.bat」。

### 增量更新（只发改动过的资源）

改一张图就要让玩家重下整个 `assets.stmdec`？不用。资源包索引里记了每个文件的
`sha256` 和大小，对比新旧两版就能只导出改动过的部分：

```bash
python tools/patch.py demo --old 旧发布目录 --out dist/补丁 --key 我的口令
```

产出 `patch.stmdec`（只含新增 / 改动的资源）和 `patch.json`（含被删资源的清单）。
把这两个文件丢进玩家的发布目录，游戏启动时会**优先读补丁**；没有补丁包时行为和以前
完全一样。口令与加密格式跟主资源包共用一套，不用另配。

---

## 发布为 HTML

```bash
python tools/htmlpub.py demo
python tools/htmlpub.py projects/我的游戏 --out dist/我的游戏_web
python tools/htmlpub.py demo --engine js       # 用页面内置解释器，完全离线
python tools/htmlpub.py demo --inline          # 素材内联，出一个单文件 HTML
python tools/htmlpub.py demo --no-assets       # 只出播放器，不带素材
python tools/htmlpub.py demo --pyodide https://你的镜像/pyodide/v0.26.2/full/
```

产出：

```
dist/我的游戏_web/
├── index.html      双击就能玩，也能直接丢到 GitHub Pages
└── assets/         图片和音频
```

**引擎跑的是 Python，不是重写一遍。** 默认用 [Pyodide](https://pyodide.org/)（WebAssembly 里的
CPython）在浏览器里加载 `stmg` 的 `parser.py` / `runtime.py`，剧本解析、变量求值、分支推进
跟桌面版是**同一份代码**，所以网页上不会出现「和桌面版表现不一样」的问题。
`stmg/web_bridge.py` 就是那层桥：JS 负责画界面收键盘，逻辑全交给 Python。

### 先把 Pyodide 拉到本地（推荐）

```bash
python tools/get_pyodide.py           # 约 13MB，下到 stmg/pyodide/
```

下过之后，`htmlpub.py` 会**自动把这份 Pyodide 打包进发布目录**（产物里的 `pyodide/`），
浏览器从同目录加载：不联网、不跨域、打开就进。国内从 jsdelivr 拉那 9.6MB 的 wasm 经常
拉不动，所以强烈建议先跑这一步。脚本有多源兜底（jsdelivr → fastly → unpkg → npmmirror），
已经下好的文件会跳过，断了重跑就行。

本地没有那份文件时才退回 CDN；CDN 也拉不到就会自动切到页面内置的轻量解释器，游戏照常能玩。

> **一个浏览器限制**：`file://` 直接双击打开的网页**不能**加载 WebAssembly（浏览器不让 fetch wasm），
> 这种情况页面会明确告诉你并自动回退。想跑 wasm 就用 http 服务打开（`python -m http.server`），
> 或者直接上传到网站。

### 网页版里的联网与文件操作

第 2 期把这两样补上了（wasm 引擎和内置解释器都支持）：

- **`R.api` 走 `fetch`**，不是被跳过。请求超过 **10 秒**没回来就放弃、`STM.API` 留空，
  剧情**照常往下走**，绝不会冻住页面（网页里没有同步请求这回事）。
  跨域要对方接口允许 CORS，否则一样算失败。
- **密钥在网页版里必然可见**：剧本里写了什么，玩家打开源码就能看到。
  要发到网上就别填明文，改成 `key=option` 从 `options.stm` 取 —— 但那也只是「稍微藏一下」，
  真敏感的东西不要交给浏览器。
- **`stm.os` 落在浏览器沙箱（IndexedDB）里**，语义和桌面版对齐，但碰不到真实磁盘。
  详见上面「网页版里的 `stm.os`」。

发布时如果剧本里用到了这两样，`htmlpub.py` 会顺手打印一条提醒，别漏看。

### 自检：确认引擎真的在跑

在地址后面加 `?selftest=1`，页面会后台跑一遍引擎，把事件流打在标题界面底部：

```
自检 [wasm] > bg > bgm > say > say > say > toast > say > choose > se > picture > say ...
```

开头的中括号是引擎来源：`[wasm]` = 真 Python 引擎跑在 WebAssembly 里，`[js]` = 内置解释器。
发布前瞄一眼，就知道这份网页到底有没有吃到真引擎。

网页版带的功能：打字机、点击 / 空格 / 回车推进、`Ctrl` 快进、`A` 自动、`H` 历史、
存读档（浏览器 localStorage，1 个自动 + 6 个手动）、音量与文字速度设置、全屏、
等比缩放铺满窗口。素材缺失会画占位块，和桌面版一个样。

> 网页版**有** `R.api` 联网和 `stm.os` 文件操作了（第 2 期补上）。
> 联网走 `fetch`（10 秒超时，失败就让 `STM.API` 留空、剧情照常推进，绝不冻住页面）；
> 文件操作全部落在浏览器沙箱（IndexedDB）里，**碰不到你的真实磁盘**。
> 两条都有前提，见下面「已知限制」。

---

## 转换成 Ren'Py

想把 STMG 的剧本搬到 Ren'Py 上跑（或者给美术 / 配音用 Ren'Py 的工具链）：

```bash
python tools/stm2renpy.py projects/我的游戏
python tools/stm2renpy.py projects/我的游戏 --out dist/我的游戏_renpy
python tools/stm2renpy.py projects/我的游戏 --no-assets     # 只转剧本
```

产出：

```
dist/我的游戏_renpy/
├── game/
│   ├── script.rpy        剧本正文，label start: 开始
│   ├── stmg_config.rpy   标题 / 分辨率 / 角色定义 / 图像定义 / 兼容变量
│   ├── images/           从 bg/ png/ gui/ 拷过来的图
│   └── audio/            从 music/ 拷过来的音频
└── 转换报告.md            转换统计 + 需要手工处理的地方
```

装好 Ren'Py SDK，新建一个空工程，把 `game/` 里的东西拷进去就能跑。

对应关系：

| STMG | Ren'Py |
|---|---|
| `S.character("角色1")` | `define 角色1 = Character("角色1")` |
| `S.cg("bg/room.png")` | `image bg_room = ...` + `scene bg_room` |
| `S.character("png/x.png", pos="left", tag="菲")` | `image 菲 x = ...` + `show 菲 x at left` |
| `S.play / sound / voice / stop` | `play music / sound / voice`、`stop music` |
| `S.hide("菲")` / `S.hide("sprite")` | `hide 菲` / 逐个 hide 在场立绘 |
| `S.jump("x")` / `S.end()` | `jump x` / `jump stmg_ending` |
| `SET 好感度 = 好感度 + 10` | `$ 好感度 = 好感度 + 10` |
| `Choose:` + `If "选项":` | `menu` + `if "选项" in stmg_chosen` |
| `Question:` | `$ stmg_answer = renpy.input(...)` |
| `"前缀" + STM.ANSWER + "后缀"` | `"前缀[stmg_answer]后缀"` |
| `**粗体**` `[color=]` `[size=]` | `{b}` `{color=}` `{size=}` |

转不了的会**写进转换报告**，不会静默丢掉：`stm.os` 文件操作、`R.api` 联网、
`STM.python` 扩展库、`python` 代码块、嵌套在分支里的 `label`、等宽标记
（Ren'Py 没有对应 tag）。

---

## 自定义界面与引擎

新建项目时引擎会**整套内嵌**进项目目录（`stmg/` 包 + `start.py` + `start.bat`），
项目完全自包含、完全开放：

```
我的游戏/
├── script.stm          主剧本
├── options.stm         配置
├── start.py / start.bat  项目自己的启动入口
├── stmg/               ★ 完整引擎源码（gui.py / render.py / markdown.py / parser.py ...）
├── custom/gui.py       界面配置
└── custom/markdown.py  自定义内联标记
```

- 跑游戏直接双击项目里的 `start.bat`，用的是**项目自己那份引擎**
- 想魔改引擎（渲染、界面、音频、语法……）**直接改项目里的 `stmg/*.py`**，
  只影响这个项目，不用碰启动器目录的源码
- 启动器跑游戏 / 语法检查 / 无头试跑时也会优先用项目内嵌的引擎
- 老项目想补：启动器里点「**内嵌引擎**」按钮即可（增量拷贝，不覆盖你改过的文件；想升级引擎就删掉项目里的 `stmg/` 再点一次）
- 删掉项目里的 `stmg/` 和 `start.py` 也能跑，会退回启动器目录的引擎

新建项目时还会在 `custom/` 下生成两个文件，引擎启动时自动加载：

```
custom/gui.py         界面长什么样
custom/markdown.py    内联标记怎么渲染
```

### custom/gui.py

里面写一个 `CONFIG` 字典，只写想改的项，其余用引擎默认值：

```python
CONFIG = {
    # 对话框：往左靠一点、矮一点、半透明
    "box_x": 0.06, "box_w": 0.72, "box_h": 0.24, "box_alpha": 215,

    # 名字框换成粉色，字大一点
    "name_size": 26, "name_bg": (214, 120, 168),

    # 立绘站位和大小
    "sprite_x": {"left": 0.22, "center": 0.5, "right": 0.78},
    "sprite_w": 0.38, "sprite_h": 0.82, "sprite_bottom": 0.80,

    # 标题界面：背景图 + 标题曲
    "title_bg": "bg/title.png",
    "title_bgm": "music/title.mp3",
    "title_top": (18, 20, 36), "title_bottom": (60, 40, 80),

    # 选择支
    "choice_w": 0.6, "choice_h": 60, "choice_gap": 20, "choice_size": 24,
}
```

能改的项和默认值全在 `stmg/uiconf.py` 的 `DEFAULTS` 里，每条都有注释。图片 / 音乐写
相对项目目录的路径，文件不存在会自动回退（比如标题背景图没放，就还是渐变）。
写错了也不会崩，开发模式下右上角会弹一句提示。

### custom/markdown.py

默认长这样：

```python
from stmg import markdown as _md

def render(text):
    return _md.render(text)
```

想加自己的标记就在 `return` 之前动手：

```python
def render(text):
    text = text.replace("[w]", "……")      # 自己的写法
    return _md.render(text)                # 剩下的交给引擎
```

返回值是 run 列表（`{"t": 文字, "bold": ..., "color": ..., "size": ...}`），
写法说明写在模板文件的注释里。改坏了会在游戏里提示，不会黑屏。

> 网页版发布时也会读 `custom/gui.py`：文字大小、对话框高度、标题背景图会翻成 CSS；
> 其余（名字框颜色、立绘站位…）是 pygame 专属的，网页用自己的一套。

---

## 美化包（mod/）—— 换主题

想给 STMG 换个外观，但不想碰引擎源码？**美化包**就是干这个的，和给编辑器
换主题一个意思：`mod/` 下放一个文件夹，写上外观参数和样式，启用即生效。

```
mod/
├── active.json          当前启用哪个包
├── none/                默认包：什么都不改，引擎原生外观
├── example_sakura/      示例包：粉白配色 + 落樱粒子
└── 你自己的包/          照上面两份抄一份就能改
```

一个美化包长这样：

```
我的主题/
├── mod.json       清单：包名 / 版本 / 作者 / 说明
├── gui.py         桌面端外观参数（只能写 CONFIG 字典）
├── theme.css      网页版样式（发布 HTML 时内联进去）
├── theme.js       网页版行为，跑在受限沙箱里
└── 素材            图片 / 音频 / 字体，路径相对本目录
```

`gui.py` 就这么点东西 —— **只能声明，不能执行**：

```python
"""我的主题。"""

CONFIG = {
    "box_radius": 16,
    "name_bg": (226, 138, 178),
    "title_top": (58, 34, 58),
    "title_bottom": (122, 72, 110),
}
```

能改哪些项、默认值多少，全在 `stmg/uiconf.py` 的 `DEFAULTS` 里（每条有注释），
只写想改的即可。外观三层叠加，后面的覆盖前面的：

```
引擎默认值  <  当前美化包  <  项目自己的 custom/gui.py
```

### 用起来

```bash
python start.py demo/script.stm --mod example_sakura     # 这次用这个包
python start.py demo/script.stm --no-mod                 # 这次不用任何包
python tools/htmlpub.py demo --mod example_sakura        # 网页版也带上

python tools/modcheck.py                                 # 看有哪些包、当前启用哪个
python tools/modcheck.py example_sakura                  # 详细检查
python tools/modcheck.py --use example_sakura            # 切到某个包
python tools/modcheck.py --new 我的主题                   # 生成新包骨架
python tools/modpub.py 我的主题                            # 打包成「我的主题_美化包」
```

启动器里点「**美化包**」按钮也行：列表、启用、新建、检查、发布都在那一个窗口里。
项目内嵌引擎时，启动器会把当前美化包的**绝对路径**传给游戏进程，所以全局主题
对内嵌引擎的项目一样生效。

### ⛔ 三条硬性限制

美化包是**主题**，不是**引擎补丁**。下面三条会**静态检查**，不合格的直接拒绝发布
（`tools/modcheck.py` 和 `tools/modpub.py` 都是逐字节检查的）：

1. **不许出现任何可执行的 Python 代码。** `gui.py` 里只允许「文档字符串 +
   `CONFIG = {字面量}`」：不许 `import`、不许函数 / 类、不许任何函数调用
   （`open` `eval` `exec`…）、不许引用 `stmg` `os` `sys` 之类的模块名。
   CONFIG 的值只能是数字 / 字符串 / 元组 / 列表 / 嵌套字典。
   → **所以「用美化包改引擎行为」在格式上就是不可能的。**
   想改引擎（渲染、语法、音频、存档逻辑……）请直接改 `stmg/` 里的源码，
   那才是引擎该改的地方；那属于你自己的 fork，不是美化包。
2. **不许带引擎本体和任何可执行文件。** 没有 `stmg/`、`tools/`、`stmenc/`、
   `pyodide/`，没有 `start.py`、`launcher.py`、`requirements.txt`，
   没有 `.exe` `.bat` `.dll` `.pyd` `.pyc` `.zip`…… 只允许 `.py`（就那一个 `gui.py`）、
   `.css`、`.js`、`.json`、`.md`、`.txt` 和图片 / 音频 / 字体。
3. **不许对外发请求、不许碰存档。** CSS 禁 `@import` 和远程 `url()`；
   `theme.js` 禁 `eval` / `new Function` / `fetch` / `XMLHttpRequest` /
   `localStorage` / `document.cookie` / `window.location` 等等。
   `theme.js` 能用的只有 `STMGTheme` 一个入口：

```js
STMGTheme.register({
  name: "我的主题",
  css: "",                  // 可选：顺手塞段样式
  onReady(api)  {},         // 页面就绪
  onTitle(api)  {},         // 回到标题画面
  onSay(api, line) {},      // 每句台词（line = {who, text}，只读）
  onChoose(api, opts) {},   // 选择支出现
  onEnding(api) {},
});
```

`api` 里只有 `stage` / `el(sel)` / `layer(name)` / `palette()` / `rect()` /
`on / off / watch` / `log(msg)` —— 够做装饰层、粒子、光效、闪光，
不够改剧情、改存档、改引擎。

> 包不合格时引擎**安全回退**到原生外观，不会崩；开发模式下右上角会说明原因。

### 发布的是「美化包」，不是 STMG 本体

```bash
python tools/modpub.py example_sakura
```

产出：

```
dist/mods/樱花飘落_美化包/
├── 安装说明.md         第一行就写明「这是美化包，不是 STMG 本体」
├── 校验报告.txt        查过什么、有哪些提示
└── example_sakura/     ← 这一层丢进 mod/ 就能用
dist/mods/樱花飘落_美化包.zip
```

`modpub.py` **只会**产出美化包：不含引擎、不含剧本、不含启动器、不含任何可执行文件，
名字里也一定带「美化包」。想发布游戏本体请用 `stmenc/start.py`（打包发布）或
`tools/htmlpub.py`（发布为 HTML）——那是另外两件事，别混。

完整规范、常见问题和踩坑都在 [`mod/README.md`](mod/README.md)。

---

## 关于加密（重要）

`.stmdec` 的文件格式是：

```
STMG + 版本 + salt + nonce + 密文 + HMAC-SHA256 校验
密钥派生：PBKDF2-HMAC-SHA256（12 万轮）
密钥流　：HMAC-SHA256
```

改一个字节就会校验失败（自检里有测这条）。

**但这是防小白，不是安全机制。** 原因很简单：

1. 口令必须写在启动器 / exe 里，玩家认真找一定翻得出来
2. 玩家只要肯花时间，什么加密都能破

它只能做到「双击打不开、随手改不了」。**所以：绝对不要在剧本或 options 里放真的 API Key。**

---

## 已知限制

- **没有移动端**：Android / iOS 都还没做（头部 `Pack=` 字段就是给它预留的）。引擎逻辑本身
  不依赖 pygame —— `Runtime` + `Session` 可以完全无头跑，移植时主要是重做渲染与输入层。
- **网页版的联网和文件操作有条件**：`R.api` 在网页版改用 `fetch` 发（不再直接跳过），
  但 10 秒拿不到结果就放弃、`STM.API` 留空，跨域还需要对方接口允许 CORS；
  密钥写在剧本里就是**必然可见**的（谁都能读网页源码），别把私钥发到网上。
  `stm.os` 只写进浏览器的 IndexedDB 沙箱（`remove` 进虚拟回收站、`revision` 先留 `.bak`），
  碰不到真实磁盘，清空站点数据就没了；浏览器不支持或用户拒绝时退回「跳过 + 提示」。
  内置解释器（`--engine js`）同样支持这两样，语义和 wasm 引擎对齐。
- 网页版的 WebAssembly 引擎需要 http 打开（`file://` 直开会被浏览器拦住 wasm），
  另外发布目录会多出 `pyodide/`（约 13MB），介意体积可以用 `--pyodide cdn` 走 CDN
- 音频格式取决于 pygame：mp3 / wav / ogg 稳妥，flac 要看你装的 SDL_mixer 版本，
  放不出来时会提示你转格式
- `include` 是解析期正文内联，公共段落必须写在主流程走不到的末尾（见上面的说明）
- `S.picture` 和立绘的基准位置仍走 `custom/gui.py` 的默认值；剧本里能逐句调的是
  `pos` / `scale` / `alpha` / `y` / `rotate`
- STMG → Ren'Py 是单向尽力转换：`stm.os` / `R.api` / `STM.python` / 嵌套 label
  转不过去，会列在转换报告里等你手工处理
- 对话历史（回顾）只保留最近若干条，读档会重置

---

## 常见问题

**Q：跑起来全是彩色色块，图呢？**
A：那是素材缺失时的占位块。把图放进项目的 `images/` 或 `bg/`、`png/` 下，路径对上就好。`tools/check.py` 会列出所有找不到的素材。

**Q：为什么缩进错了不报错，只是不生效？**
A：分支范围就是靠缩进判定的，缩进不对解析器会当你在写平级语句。`--check` 会对可疑的缩进给出提示。

**Q：能做成 exe 吗？**
A：能。`stmenc/start.py` 会生成一个 `打包成exe.bat`，用 PyInstaller 封。

**Q：为什么启动器是 CustomTkinter，游戏却是 pygame？**
A：启动器是开发工具，要的是树形列表、面板、对话框这些现成控件，CustomTkinter 开箱就是现代观感（圆角、深浅色跟随系统），比自己写一套省事得多；游戏要的是像素级的渲染控制力，所以用 pygame。两者互不依赖——引擎坏了启动器照样开，反过来也一样。

**Q：支持中文变量名吗？**
A：支持。`SET 好感度 = 0` 完全合法。

---

## 参与开发

欢迎提 Issue 和 PR。

改引擎之前建议先跑一遍自检：

```bash
python tools/selftest.py
```

加新语法的话，顺手在 `demo/script.stm` 里补一个用例，自检就能覆盖到。

---

## 许可

[MIT](LICENSE)

---

*设计：ciallo0721-cmd*
