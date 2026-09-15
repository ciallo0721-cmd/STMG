# mod/ —— STMG 美化包

这里放**外观定制包**。想给 STMG 换个样子（配色、对话框、名字框、标题界面、
网页版样式和动效），在 `mod/` 里新建一个文件夹改就行 —— 和给编辑器换主题一个意思。

```
mod/
├── active.json          当前启用哪个包
├── none/                默认包：什么都不改，引擎原生外观
├── example_sakura/      示例包：粉白配色 + 落樱粒子，可以直接启用看效果
└── 你自己的包/          照 none/ 或 example_sakura/ 抄一份就开始改
```

## 一个美化包长什么样

```
我的主题/
├── mod.json       清单：包名 / 版本 / 作者 / 说明（必须）
├── gui.py         桌面端外观参数（必须，只能写 CONFIG 字典）
├── theme.css      网页版样式（可选）
├── theme.js       网页版行为，跑在受限沙箱里（可选）
└── 其他素材        图片 / 音频 / 字体，随便放，路径相对本目录
```

`mod.json`：

```json
{
  "kind": "beautify",
  "id": "sakura",
  "name": "樱花飘落",
  "version": "1.0.0",
  "author": "你的名字",
  "desc": "粉白配色 + 落樱粒子。",
  "files": {"gui": "gui.py", "css": "theme.css", "js": "theme.js"}
}
```

`gui.py` 只能长这样 —— 文档字符串 + 一个 CONFIG 字典，别的什么都不许写：

```python
"""我的主题。"""

CONFIG = {
    "box_radius": 16,
    "name_bg": (226, 138, 178),
    "title_top": (58, 34, 58),
    "title_bottom": (122, 72, 110),
}
```

能写哪些项、默认值是多少，全在 `stmg/uiconf.py` 的 `DEFAULTS` 里，每条都有注释。
**只写想改的项**，没写的用引擎默认值。

## 怎么启用

改 `active.json`：

```json
{ "mod": "example_sakura" }
```

或者用启动器：点「美化包」→ 选中 → 启用。也可以临时指定，不动配置文件：

```bash
python start.py demo/script.stm --mod example_sakura
python start.py demo/script.stm --mod example_sakura --check
python start.py demo/script.stm --no-mod          # 这一次不用任何美化包
```

优先级（后面的覆盖前面的）：

```
引擎默认值  <  当前美化包  <  项目自己的 custom/gui.py
```

也就是说，项目里那份 `custom/gui.py` 最大 —— 一个项目想压过全局主题，
在它自己的 `custom/gui.py` 里写就行了。

新建一个包最省事的做法：

```bash
python tools/modcheck.py --new 我的主题            # 生成骨架
python tools/modpub.py  我的主题                   # 检查 + 打包成「我的主题_美化包」
```

启动器里也有对应的按钮。

---

## ⛔ 三条硬性限制（会静态检查，不合格发不出去）

美化包是**主题**，不是**引擎补丁**。下面三条不是建议，是 `tools/modcheck.py`
逐字节检查的东西，违反了直接拒绝发布。

### 1. 不许出现任何可执行的 Python 代码

`gui.py` 里只允许「文档字符串 + `CONFIG = {字面量}`」。具体禁止：

- `import` / `from ... import ...`
- 函数、类、lambda、装饰器
- 任何函数调用（`open()`、`eval()`、`exec()`、`print()`…）
- 引用模块或变量（`stmg`、`os`、`sys`、`__builtins__`…）
- 给 `CONFIG` 以外的名字赋值

CONFIG 里的值只能是**字面量**：数字、字符串、元组、列表、嵌套字典。
写 `"box_h": 0.3` 行，写 `"box_h": calc(1)` 不行。

> 为什么这么严？因为美化包只要还能执行一行代码，就能改引擎、就能干别的。
> 干脆从格式上堵死 —— **美化包只能声明外观，永远改不了行为**。

想改引擎行为（渲染、语法、音频、存档逻辑……）？在 `stmg/` 里改源码，
那是引擎该改的地方。改了引擎就自己 fork，那不是美化包该干的事。

### 2. 不许带引擎本体和任何可执行文件

- 不许有 `stmg/`、`tools/`、`stmenc/`、`pyodide/`、`dist/`、`.git/`
- 不许有 `start.py`、`launcher.py`、`__init__.py`、`requirements.txt`、`setup.py`
- 不许有 `.exe` `.bat` `.cmd` `.ps1` `.sh` `.vbs` `.dll` `.pyd` `.pyc` `.jar` `.lnk`…
- 只允许 `.py`（就那一个 `gui.py`）、`.css`、`.js`、`.json`、`.md`、`.txt`
  和图片 / 音频 / 字体

### 3. 不许对外发请求、不许碰存档

样式（`theme.css`）：

- 禁 `@import`、`expression()`、`javascript:`、`behavior:`、`-moz-binding`
- `url()` 不能指向远程地址（`http://`、`https://`、`//`）—— 素材必须自带

脚本（`theme.js`）：

- 禁 `eval` / `new Function` / 动态 `import()` / `require()`
- 禁 `fetch` / `XMLHttpRequest` / `WebSocket` / `sendBeacon`（不能联网）
- 禁 `localStorage` / `sessionStorage` / `indexedDB` / `document.cookie`
  （存档就在这里，不许碰）
- 禁 `window.location` / `parent` / `top` / `opener` / `postMessage`（不能跳走、不能打洞）
- 禁访问引擎内部（`__STMG*`、`pyodide`、存档函数）

`theme.js` 能用的只有 `STMGTheme` 这一个入口：

```js
STMGTheme.register({
  name: "我的主题",
  css: "",                    // 可选：顺手塞一段样式
  onReady(api)  {},           // 页面就绪
  onTitle(api)  {},           // 回到标题画面
  onSay(api, line) {},        // 每句台词（line = {who, text}，只读）
  onChoose(api, opts) {},     // 选择支出现（opts 只读）
  onEnding(api) {},
});
```

`api` 里只有：`stage`、`el(sel)`、`layer(name)`、`palette()`、`rect()`、
`on / off / watch`、`log(msg)`。够做装饰层、粒子、光效、闪动，
不够改剧情、改存档、改引擎。

---

## 检查与发布

```bash
python tools/modcheck.py                 # 列出所有包 + 当前启用哪个
python tools/modcheck.py example_sakura  # 单个包的详细检查
python tools/modcheck.py --new 我的主题   # 生成新包骨架

python tools/modpub.py 我的主题           # 校验通过后打包
```

`modpub.py` 只会产出 **`dist/mods/我的主题_美化包/`**（外加同名 zip），
里面带一份写清楚「这是美化包，不是 STMG 本体」的说明文件 ——
**它永远不含引擎、不含剧本、不含启动器**。想发引擎本体请用
`stmenc/start.py`（打包发布）或 `tools/htmlpub.py`（发布为 HTML），
那是两回事，别混。

只要有 `error` 级别的违规，`modpub.py` 就直接拒绝打包，不会给你留后门。

---

## 常见问题

**Q：我改的包没生效？**
先跑 `python tools/modcheck.py`。它会把不合格的包标出来，启动器日志里也会说
为什么回退到原生外观。包一旦不合格，引擎会**安全回退**，不会崩。

**Q：桌面端和网页版为什么不一样？**
桌面端读 `gui.py`（pygame 渲染），网页版读 `theme.css` + `theme.js`（DOM/CSS）。
同一个配色要两边一致，就得两边都写一份 —— 这是没办法的事，两套渲染管线。
`gui.py` 里能对应上的项（正文字号、对话框高度、标题背景图）发布网页时会自动翻成 CSS。

**Q：美化包里的图片怎么引用？**
桌面端：`"title_bg": "bg/title.png"`。引擎先在这个项目里找，找不到就用美化包目录里的
那份同名文件，所以放美化包自己的 `bg/` 下就行。
网页版：CSS 里直接 `url("bg/title.png")`，发布时会自动拷出去并改好路径。

**Q：能让美化包改引擎的某个功能吗？**
不能，这是设计好的。美化包 = 换主题。要改功能就改 `stmg/` 源码 ——
你的修改属于你自己的 fork，别指望用「美化包」的名义发出去。
