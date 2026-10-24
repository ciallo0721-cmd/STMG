# STMG 在线制作器

在浏览器里写剧本、跑预览、导出成品的一套工具。整个东西是静态文件，不需要后端，
丢到任何静态托管（GitHub Pages / Nginx / `python -m http.server`）都能用。

## 怎么跑起来

**不能直接双击 `index.html`。** 浏览器在 `file://` 下禁止加载 WebAssembly，
引擎起不来，页面会一直停在「引擎没起来」。

正确姿势：

```bash
cd dist/maker
python -m http.server 8000
# 浏览器打开 http://localhost:8000/
```

或者丢到 GitHub Pages 上，直接访问仓库地址。

## 界面

```
┌ 顶栏：新建 / 导入 / 导出 / 体检 / 运行 ─────────────────────┐
│ 文件树  │  编辑器（语法高亮 + 行号 + 错误红点）  │  实时预览  │
│         │  问题面板（点一行跳过去）            │            │
└ 状态栏：引擎状态 · 剧本行数 · 素材大小 · 体检结果 ───────────┘
```

### 快捷键

| 键 | 作用 |
|---|---|
| `Ctrl+N` | 新建项目 |
| `Ctrl+O` | 导入（zip / 素材） |
| `Ctrl+S` | 立刻保存（平时 900ms 自动存） |
| `Ctrl+F` | 查找替换 |
| `Ctrl+B` | 体检 |
| `Ctrl+W` | 关当前标签 |
| `F5` | 运行预览 |
| `Shift+F5` | 停止预览 |
| `Tab` / `Shift+Tab` | 缩进 / 反缩进（多行选中时整块缩进） |

### 编辑器的几个小动作

- 回车自动跟上一行缩进，`If:` / `Choose:` / `Repeat:` / `While:` 结尾会自动多缩一级
- 行首 4 个空格按一下退格 = 退一级
- 错误行左边行号变红，鼠标点问题面板那一行会跳过去
- 剧本改动后 800ms 自动体检，缺素材也会列出来

## 素材

素材按**相对路径**引用，和桌面版一致：

```
bg/room.png      →  剧本里写 S.cg("bg/room.png")
music/bgm.mp3    →  剧本里写 S.play("music/bgm.mp3")
```

导出时这些文件会原样进 `assets/`，播放器内部把 `bg/room.png` 映射成
`assets/bg/room.png`，剧本不用改。

上传方式：点侧栏的 `↑`，或者直接把文件 / 整个文件夹拖进窗口。
拖文件夹会保留目录结构。

## 导出

点右上角「导出」，四种：

| 格式 | 产物 | 适合 |
|---|---|---|
| **桌面版**（推荐） | `index.html` + `assets/` + `pyodide/` + `启动游戏.bat` + `serve.ps1` + exe 打包脚本 | 发给别人玩 |
| **网页版** | 同上但去掉启动器 | 丢 GitHub Pages |
| **单个 HTML** | 一个 `.html`，素材全 base64 内联 | 小项目、单文件分享 |
| **项目源包** | 只有 `.stm` 和素材 | 备份 / 给桌面版 STMG 仓库 |

### 关于 exe

浏览器**没法直接编译 exe**——那需要本机的 Python 和 PyInstaller。
所以「桌面版」包里放的是：

```
启动游戏.bat      双击 → 用 Windows 自带的 PowerShell 起 http 服务 + 开浏览器
serve.ps1         那个服务（零依赖，不用装 Python）
serve.py          Python 版服务器（可选）
start_game.py     装了 Python 的话双击也行
打包EXE.bat       装了 Python 后双击 → 自动装 PyInstaller 并打包
build_exe.py      打包脚本本体
exe_main.py       exe 的入口
```

`打包EXE.bat` 会生成 `dist/STMG-Game.exe`，30~40MB。
它的本质是「内置 http 服务 + 启动浏览器」，不是原生游戏程序——因为引擎本身
是 WebAssembly 里的 CPython，只能跑在浏览器里。

### 关于启动器为什么必须走 http

`index.html` 里内联了引擎源码，引擎本身在 `pyodide/pyodide.asm.wasm`。
浏览器加载 wasm 要求同源 http(s)，`file://` 会被 CORS 挡死。
`serve.ps1` 就是干这个的，所以别删。

## 目录

```
index.html               制作器外壳
css/app.css              界面样式
js/editor.js             编辑器（高亮 / 行号 / 缩进 / 查找）
js/storage.js            IndexedDB 项目存储 + 手写 zip 读写
js/engine.js             Pyodide 桥（体检 / 运行驱动）
js/player.js             播放器（预览和导出共用同一份）
js/exporter.js           导出器
js/app.js                主控
js/engine-src.js         ← 构建生成：整个 stmg 引擎的 Python 源码
js/pyodide-manifest.js   ← 构建生成：pyodide 文件清单
pyodide/                 WebAssembly 引擎（一个 .wasm + 几个 .js + stdlib.zip）
```

`js/engine-src.js` 和 `js/pyodide-manifest.js` 是 `tools/build_maker.py` 生成的，
不要手改。改了源码之后的正确流程：

```bash
python tools/build_maker.py
```

## 和桌面版的关系

预览和导出跑的都是 **同一份 `stmg/*.py`**，通过 Pyodide 在浏览器里执行。
所以剧本的解析、变量求值、分支推进、`R.api`、`stm.os` 的行为和桌面版一致
（`R.api` 受浏览器 CORS 限制，`stm.os` 落在浏览器沙箱里——这两点在网页版
是环境限制，不是引擎差异）。

## 已知限制

- **不能直接 `file://` 打开**，必须 http。
- **首次加载约 10MB**（wasm 本体），之后浏览器会缓存。
- **美化包（`mod/`）不生效**：文件树能看到，但预览和导出不会注入 `theme.css/js`。
  用桌面版发布才会带上。
- **`custom/gui.py` 只认几个字段**：`text_size`、`box_h`、`title_bg` 会被
  正则抠出来用于预览；其它界面逻辑不会执行。
- **exe 需要本机装 Python** 才能打包，浏览器里做不了。
- **单个 HTML 模式**素材是 base64，体积会涨 1/3，超过 24MB 会提示改用桌面版。
