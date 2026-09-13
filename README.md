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

---

## 目录

- [特性](#特性)
- [快速开始](#快速开始)
- [语法速查](#语法速查)
- [完整语法手册](#完整语法手册)
- [游戏内错误界面](#游戏内错误界面解析错误不进命令行)
- [项目结构](#项目结构)
- [命令行工具](#命令行工具)
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
- **带语法检查器** —— `--check` 逐行报错，五级错误分级，写错了不用开着窗口试
- **加密发布** —— 一键把剧本和素材打包成 `.stmdec`，纯标准库实现，零额外依赖
- **缺素材不崩** —— 图还没画好也能跑，引擎会自动画占位块
- **图形化启动器** —— 项目管理、新建模板、检查、试跑、打包、发布，点点鼠标就行
- **发布成网页** —— 一键生成能直接玩、能分享的 HTML，逻辑跑的是**真引擎**（WebAssembly，不是重写一遍）
- **能转 Ren'Py** —— 剧本可以反向导出成 `.rpy`，想换引擎不用重写
- **界面可自定义** —— 项目里的 `custom/gui.py` 随便改：对话框位置、名字框颜色、标题图、标题曲

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
```

### 操作

| 操作 | 按键 |
|---|---|
| 推进 | 鼠标左键 / `空格` / `回车` |
| 历史记录 | 滚轮上翻 / `H` |
| 自动播放 | `A` |
| 快进 | 按住 `Ctrl` |
| 存档 / 读档 | `F5` / `F9` |
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
| `R.api(url="...", key=option)` | 发 HTTP 请求，结果在 `STM.API` |
| `stm.os(read("C:/a.txt"))` | 读文件，内容进 `STM.OS`（静默，不弹提示） |
| `stm.os(create("C:/a.txt"))` | 建空文件（已存在则不动） |
| `stm.os(remove("C:/a.txt"))` | 删文件（移回收站，不是永久删） |
| `stm.os(revision("C:/a.txt"),"旧"to"新")` | 改文件，先留 `a.txt.bak` 备份 |

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

> ⚠️ **伦理与合规**：这种能力本质是读写玩家机器上的文件。请只用于
> **自己电脑上的演示**，或**玩家明确知情同意**的演出（比如读写游戏**自己**的存档目录）。
> 拿它去偷窥、破坏别人文件既违法又不道德——那种情况被抓到是真的会穿帮的。

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
│   ├── uiconf.py            界面配置：默认值 + 读项目里的 custom/gui.py
│   ├── render.py            排版、文本框、立绘布局
│   ├── audio.py             BGM / 音效 / 语音
│   ├── markdown.py          内联标记 → 样式片段
│   ├── web_bridge.py        网页版桥：在 Pyodide 里跑这个真引擎
│   ├── webplayer.html       网页播放器模板（发布 HTML 用它渲染）
│   ├── pyodide/             WebAssembly 版 CPython 本体（tools/get_pyodide.py 下的，约 13MB）
│   ├── templates/           新建项目时拷过去的两份自定义文件
│   │   ├── custom_gui.py        界面配置模板
│   │   └── custom_markdown.py   自定义标记模板
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
│   ├── renpy2stm.py         Ren'Py 工程 → STMG
│   ├── stm2renpy.py         STMG → Ren'Py（反向）
│   ├── htmlpub.py           STMG → 网页版（HTML）
│   └── get_pyodide.py       把 Pyodide 拉到本地，网页版就能离线跑真引擎
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
```

自检覆盖 48 项，改完引擎先跑它比开窗口快得多。

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
```

产出：

```
dist/我的游戏/
├── script.stmdec      加密的主剧本
├── options.stmdec     加密的配置
├── assets.stmdec      素材打成一个加密资源包
├── stmg/              引擎本体
├── start.py           生成的启动器（口令写在里面）
├── start.bat          双击运行
└── 打包成exe.bat      用 PyInstaller 封成单文件 exe
```

封 exe 需要先装 PyInstaller：

```bash
pip install pyinstaller
```

然后双击发布目录里的「打包成exe.bat」。

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

> 网页版没有 `R.api` 联网（浏览器里同步请求不现实，已挡掉）和 `stm.os` 文件操作
> （虚拟文件系统里没有你的真磁盘）。这两样在剧本里出现会静默跳过。

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
`STM.python` 扩展库、嵌套在分支里的 `label`、等宽标记（Ren'Py 没有对应 tag）。

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

- 没有转场特效（淡入淡出、溶解），只做图层切换
- 立绘不支持缩放、旋转、表情差分（`at` 只认左右中）
- 存档用「记录玩家选择 + 重放」实现；如果剧本里有随机数或 `R.api` 产生的分支，读档可能对不上
- 没有 CG 回廊、多语言切换、跳过已读
- `S.picture` 和立绘的位置走 `custom/gui.py` 的默认值，剧本里没法逐句改
- 音频格式取决于 pygame，mp3 / wav / ogg 能放，flac 不行
- 错误提示的措辞还偏开发者向
- 网页版没有 `R.api` 联网（浏览器里同步请求不现实）和 `stm.os` 文件操作，
  这两样在剧本里出现会静默跳过
- 网页版的 WebAssembly 引擎需要 http 打开（`file://` 直开会被浏览器拦住 wasm），
  另外发布目录会多出 `pyodide/`（约 13MB），介意体积可以用 `--pyodide cdn` 走 CDN
- STMG → Ren'Py 是单向尽力转换：`stm.os` / `R.api` / `STM.python` / 嵌套 label
  转不过去，会列在转换报告里等你手工处理

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
