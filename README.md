# STMG — Super Text Markdown Galgame

一个用 Python + pygame 写的最小可用视觉小说引擎。
语法、UI、目录结构来自你的设计稿《Super Text Markdown Galgame language》，
实现里凡是设计稿没写死的地方，都在下面 **§4 补充约定** 里单独标了出来。

当前状态：**能跑通全流程**（解析 → 剧情推进 → 界面 → 存读档 → 加密发布）。
自检 23 项全过。

---

## 1. 快速开始

环境已经建好了（虚拟环境在 `STMG/.venv`，装在 G 盘，没碰 C 盘）。

### 用启动器（推荐）

```bat
:: 双击这个，或者
STMG启动器.bat
```

启动器是**普通 Python + tkinter** 写的（标准库自带，不用装东西）。
左边选项目，右边点按钮：**启动游戏 / 语法检查 / 无头试跑 / 打包发布 / 编辑剧本 / 打开文件夹**。

第一次用点「新建项目」，会生成一份能直接跑的模板：

```
projects\<你的项目>\
├── script.stm      主剧本（模板里已经带了变量、选择支、询问的示例）
├── options.stm     标题 / 加密口令 / 打包规则
├── README.md
├── bg\   背景图
├── png\  立绘、贴图
├── music\  BGM / 音效 / 语音
└── gui\  文本框、按钮图片（不放就用默认样式）
```

> 为什么不像 Ren'Py 那样用剧本语言自举启动器？
> 启动器要处理原生文件对话框、子进程、滚动列表这些活，用剧本语言反而要造一堆轮子。
> 用 tkinter 写更短、更稳，出问题也更好查。引擎本身还是 pygame。

### 命令行（不开启动器）

```bat
:: 无参数 -> 打开启动器；带参数 -> 直接跑剧本
start.bat
start.bat demo\script.stm
start.bat projects\我的游戏\script.stm
```

手动命令（CMD）：

```bat
cd /d "G:\workbuddymoren\2026-09-11-21-08-11\STMG"
.venv\Scripts\python.exe start.py                    :: 跑 demo，开窗口
.venv\Scripts\python.exe start.py 我的游戏\script.stm  :: 跑自己的剧本
.venv\Scripts\python.exe start.py --check demo\script.stm   :: 只看语法，不开窗
.venv\Scripts\python.exe start.py --auto demo\script.stm    :: 无头跑一遍，打印所有台词
.venv\Scripts\python.exe start.py --auto=1 demo\script.stm  :: 自动选第二个选项
.venv\Scripts\python.exe start.py --release demo\script.stm :: 按发布版规则跑
```

改完剧本的推荐流程：**先 `--check` → 再开窗口**。

### 自检 / 打包

```bat
.venv\Scripts\python.exe tools\selftest.py            :: 23 项自检
.venv\Scripts\python.exe tools\check.py demo --verbose  :: 语法检查 + 语句树
.venv\Scripts\python.exe stmenc\start.py demo          :: 加密打包到 dist\demo
dist\demo\start.bat                                     :: 试跑发布版
```

---

## 2. 目录结构

```
STMG/
├── launcher.py              启动器（tkinter）
├── STMG启动器.bat           双击打开启动器
├── start.py / start.bat     剧本启动器：跑一个 script.stm
├── projects/                你的项目都放这
├── .venv/                   虚拟环境（pygame 在这）
├── stmg/                    ★ 引擎核心，剧本作者不用改这里
│   ├── errors.py            五级错误体系
│   ├── parser.py            .stm → 语句树
│   ├── markdown.py          md 内联标记 → run 列表
│   ├── runtime.py           语句树 → 事件流（生成器）
│   ├── session.py           推进器：当前显示什么 / 点了以后变什么 / 存读档
│   ├── gui.py               pygame 主界面
│   ├── render.py            排版、文本框、立绘、占位块
│   ├── audio.py             BGM / SE / Voice 三通道
│   ├── options.py           options.stm 解析
│   ├── save.py              存档槽读写
│   ├── crypto.py            .stmdec 加解密
│   ├── pack.py              发布版资源容器
│   ├── project.py           项目的发现 / 新建 / 移除
│   └── stdlib_api.py        STM.python 白名单 + R.api 联网
├── stmenc/start.py          加密打包器（设计稿里的 STMENC）
├── tools/check.py           语法检查器
├── tools/selftest.py        自检
├── demo/                    示例游戏（故意不放素材，验证占位块）
└── dist/demo/               已经打好的发布版，双击 start.bat 就能玩
```

---

## 3. 语法手册

### 3.1 文件骨架

```stm
<
Size=1280x720          <-- Large= 也认
title="我的第一个游戏"
Ver="1.0.0"
Pack="com.example.example"    <-- 保留字段，暂时忽略
Lang="cn"
Font="SIMHEI"
>
<
Start:
...正文...
>
<
"感谢游玩"             <-- 结尾块，可选
>
```

三个 `< ... >` 块靠**顺序**区分：第 1 块是头，第 2 块是正文，第 3 块（可选）是结尾。

### 3.2 正文里的语句

| 写法 | 意思 |
|---|---|
| `Start:` | 起始标签（可选，没有也能跑） |
| `"台词"` | 旁白（不显示名字框） |
| `塔菲"台词"` 或 `塔菲: "台词"` | 让「塔菲」说话 |
| `<-- 注释 -->` | 注释，随便写 |
| `S.character("塔菲")` | **注册角色**（名字里没有图片后缀） |
| `S.character("png/立绘.png")` | **显示立绘**（名字看起来像图片路径） |
| `S.cg("bg/教室.png")` | 换背景 |
| `S.picture("png/纸条.png")` | 背景之上叠一张图 |
| `S.play("music/bgm.mp3")` | BGM（默认循环，`loop=false` 可关） |
| `S.sound("music/开门.wav")` | 音效（可叠加，不打断 BGM） |
| `S.voice("music/v001.wav")` | 语音（新的打断旧的） |
| `S.stop("bgm")` / `S.stop("all")` | 停音频 |
| `S.hide("sprite")` / `S.hide("all")` | 隐藏立绘 / 清空所有图层 |
| `S.jump("标签名")` | 跳到某个标签 |
| `S.end()` | 直接结束 |
| `STM.display("文字")` | 右上角弹一条提示 |
| `STM.python("turtle")` | 载入一个白名单标准库（**只有开发版能用**） |
| `R.api(url="...", key=option)` | 发一个 HTTP 请求，结果放在 `STM.API` |
| `SET 变量 = 值` | 赋值 |
| `变量 = 值` | 同上（英文变量名走这条） |

### 3.3 选择支与分支

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

- **缩进 4 格（或 Tab）= 进入上一层分支。** 这是 `If` 范围的判定方式。
- `EndIf` / `EndChoose` 可写可不写；写了也能正常工作。
- `If "选项名"` 判断的是「有没有选过这个选项」。
- `If 好感度 >= 10` 判断变量。

### 3.4 询问玩家输入

```stm
STM.Q = "请问你叫什么名字？"
Question:

"原来叫 **" + STM.ANSWER + "** 啊。"
```

- `Question:` 下面缩进一个 `"..."`，或者用 `STM.Q = "..."` 指定提示文字。
- 玩家输入的结果存在 **`STM.ANSWER`**。

### 3.5 Markdown 内联

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

### 3.6 options.stm

```stm
<
About = "显示在「关于」界面里的文字"
Enc   = "加密口令"
dec   = "*.stm,*.png,*.jpg,*.mp3,*.wav,*.ogg"   <-- 加密时打包哪些文件
AllowNet = "true"                                <-- 发布版允不允许 R.api 联网
>
```

`R.api(key=option)` 会自动从这里的 `Enc` 取值，剧本里就不用写明文密钥。

---

## 4. 设计稿之外的补充约定

设计稿里没写、但实现必须拍板的地方，全在这。**你不满意的话直接说，我改。**

| # | 项目 | 约定 | 为什么 |
|---|---|---|---|
| 1 | 用户输入存哪 | `STM.ANSWER` | 设计稿只写了 `STM.Q`（提示文字），没说输入存哪 |
| 2 | `If` / `Choose` 的范围 | 缩进 4 格 | 设计稿没有 `EndIf` 也没有缩进说明，解析器无法判断分支到哪结束。`EndIf` 也支持 |
| 3 | `R.api` 的参数 | 补逗号 `url=..., key=...` | 设计稿写的 `R.api(url="a"key="b")` 少了逗号 |
| 4 | 全角引号 | 自动纠正成半角 | 设计稿通篇是 `“ ”`，直接抄进 `.stm` 会全线解析失败 |
| 5 | `Question:` 的提示 | 下一行缩进的 `"..."`，或 `STM.Q` | |
| 6 | 变量引用 | 台词里带 `+` 或 `STM.` 才会当算式求值，其余一律当纯文本 | 不然每句台词都要转义，太痛苦 |
| 7 | `S.jump` / `S.hide` / `S.end` | 新增 | 设计稿有标签但没有跳转，有图层但没有隐藏，做长剧情会很难受 |
| 8 | 存档不存引擎状态 | 只存「玩家所有选择 + 翻到第几句」，读档时重放 | 生成器没法序列化，这是最稳的做法 |
| 9 | `STM.python` | 白名单 + 仅开发版可用 | 设计稿自己也担心隐私问题；右上角提示挡不住 `os.system` |
| 10 | 报错界面 | 开发版显示完整回溯，发布版只给一句友好提示 + 记日志 | 设计稿说「Error 只在开发环境显示」，但没说发布版给用户看什么 |

### 设计稿里我**没动**的地方

`S.character` 的双重含义**原样保留**（你选的那条）——参数像图片路径就是立绘，否则是注册角色名。
`Choose` / `If` / `SET` / `Question` 的关键字、`< >` 块定界、五级错误命名，全部按原样实现。

---

## 5. 操作说明

| 操作 | 键 |
|---|---|
| 推进 | 鼠标左键 / 空格 / 回车 |
| 历史记录 | 滚轮上翻 / `H` |
| 自动播放 | `A` |
| 快进 | 按住 `Ctrl` |
| 存档 | `F5` |
| 读档 | `F9` |
| 菜单（音量、文字速度、存读档） | `Esc` |

设置会自动保存在 `<游戏目录>/.stmg_save/settings.json`。

---

## 6. 加密与发布

```bat
.venv\Scripts\python.exe stmenc\start.py demo --out dist\demo
```

产出：

```
dist\demo\
├── script.stmdec      加密的主剧本
├── options.stmdec     加密的配置
├── assets.stmdec      gui/ 和 music/ 打成一个加密资源包
├── stmg\              引擎本体（Python 源码）
├── start.py           生成的启动器，口令写在里面
├── start.bat          双击运行
└── 打包成exe.bat      用 PyInstaller 封成单文件 exe
```

`.stmdec` 格式：`STMG` + 版本 + salt + nonce + 密文 + HMAC 校验。
密钥派生用 PBKDF2-HMAC-SHA256（12 万轮），密钥流用 HMAC-SHA256，纯标准库，零额外依赖。
改一个字节就会校验失败——这条自检里有测。

### ⚠️ 加密强度说明（重要）

**这是防小白，不是安全机制。** 原因：

1. 口令必须写在 `start.py` / `exe` 里，玩家认真找一定翻得出来；
2. 玩家只要肯花时间，什么加密都能破。

所以：**绝对不要在剧本或 options 里放真 API Key。** 它只能做到「双击打不开、随手改不了」。

---

## 7. 已知限制 / 下一步可以做的

- 立绘只有一个位置，没有表情差分、没有位置/缩放参数
- 没有转场特效（淡入淡出、溶解）—— 只做了图层切换
- 存档用「重放法」，如果剧本里有随机数或 `R.api` 产生的分支，重放可能对不上
- `S.picture` / 立绘的位置是写死的，还没做成可配置
- 音频格式取决于 pygame，mp3/wav/ogg 都能放，但放不了 flac
- 没有 CG 回廊、没有多语言切换、没有跳过已读
- 错误提示还是英文式 `->` 而不是更友好的中文长句

---

## 8. 测试清单（照着这个测，测到问题直接把现象丢给我）

- [ ] `tools\check.py` 在我故意写错行时，报错的行号对不对
- [ ] 对白 / 旁白 / 多角色切换，名字框颜色是不是每个角色不同
- [ ] `Choose` 能点，`If` 走对分支，两条分支都走一遍
- [ ] 缩进嵌套两层以上不串味（`If` 里套 `If`）
- [ ] `Question` 输入的值能在后面剧本里用（`STM.ANSWER`）
- [ ] `S.cg` / `S.picture` / 立绘，三层叠放顺序对不对
- [ ] BGM 循环、`S.sound` 不打断 BGM、`S.voice` 能打断
- [ ] Markdown 的加粗 / 颜色 / 注音在文本框里真的生效
- [ ] 存档 → 退出 → 读档，能回到同一句
- [ ] `stmenc` 打包后能跑；手动改 `script.stmdec` 一个字节，应该报「校验失败」
- [ ] 窗口拉伸 / 全屏切换
- [ ] 缺素材时画占位块，不崩
- [ ] 启动器：新建项目 → 生成的项目直接能启动
- [ ] 启动器：语法检查的输出有没有正常显示在下面的日志区
- [ ] 启动器：移除项目后，文件夹是不是躺在 `projects\_trash\` 里（不是被删）

---

## 9. 改动记录

- `stmg/parser.py`、`stmg/markdown.py` 是最早读设计稿时先写的原型，后来按最终语法重写了
- 全部代码无第三方依赖，只有 pygame（启动器只用 tkinter，连 pygame 都不需要）
- `start.bat` 无参数时改成打开启动器，带参数还是老样子直接跑剧本
- 「移除项目」不删盘，只挪到 `projects\_trash\`；引擎外的项目更是一律不动磁盘

---

*设计：ciallo0721-cmd　实现：WorkBuddy*
