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
- **图形化启动器** —— 项目管理、新建模板、检查、试跑、打包，点点鼠标就行

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
| 编辑剧本 | 用系统默认编辑器打开 `script.stm` |
| 打开文件夹 | 打开项目目录 |

第一次用点「**新建项目**」，会生成一份能直接跑的模板（自带变量、选择支、询问输入的示例）。

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
├── launcher.py              图形化启动器（tkinter）
├── STMG启动器.bat           双击打开启动器
├── start.py                 剧本启动器：跑一个 script.stm
├── start.bat                Windows 快捷入口
├── stmg/                    ★ 引擎核心
│   ├── parser.py            .stm → 语句树
│   ├── runtime.py           语句树 → 事件流
│   ├── session.py           推进器：当前显示什么 / 存读档
│   ├── gui.py               pygame 主界面
│   ├── render.py            排版、文本框、立绘布局
│   ├── audio.py             BGM / 音效 / 语音
│   ├── markdown.py          内联标记 → 样式片段
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
│   └── selftest.py          引擎自检
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

自检覆盖 33 项，改完引擎先跑它比开窗口快得多。

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
- `S.picture` 和立绘的位置是写死的，没做成可配置
- 音频格式取决于 pygame，mp3 / wav / ogg 能放，flac 不行
- 错误提示的措辞还偏开发者向

---

## 常见问题

**Q：跑起来全是彩色色块，图呢？**
A：那是素材缺失时的占位块。把图放进项目的 `images/` 或 `bg/`、`png/` 下，路径对上就好。`tools/check.py` 会列出所有找不到的素材。

**Q：为什么缩进错了不报错，只是不生效？**
A：分支范围就是靠缩进判定的，缩进不对解析器会当你在写平级语句。`--check` 会对可疑的缩进给出提示。

**Q：能做成 exe 吗？**
A：能。`stmenc/start.py` 会生成一个 `打包成exe.bat`，用 PyInstaller 封。

**Q：为什么启动器是 tkinter，游戏却是 pygame？**
A：启动器是开发工具，需要原生文件对话框和滚动列表，tkinter 是标准库、零依赖，更合适；游戏要的是渲染控制力，用 pygame。启动器连 pygame 都不需要，引擎坏了它照样能打开。

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
