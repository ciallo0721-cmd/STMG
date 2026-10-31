# 📋 STMG 功能建议报告（第 3 期 · 下一层缺口）

> 基于真实源码重新盘点。**第 2 期（2026-09-17 ~ 09-18）已确认全部落地**，本报告剔除已落地项，只挖下一层缺口。
> 生成时间：2026-10-31

## 项目概况

- **类型**：桌面视觉小说引擎 + 工具链 + 网页版 + 在线制作器
- **技术栈**：Python 3.8+ / pygame / CustomTkinter（启动器）/ Pyodide（网页真引擎）/ WebView 思路（移动端预留）
- **现有功能数**：约 55 项核心能力（含第 1、2 期全部落地项）
- **输出形态**：桌面 exe / 加密 `.stmdec` / 网页 HTML（wasm 或 js 引擎）/ Ren'Py `.rpy` / 在线 IDE（webmaker）/ 美化包

## 已剔除 / 已落地（本期不再建议）

| 原以为缺 | 实际状态 | 证据 |
|---|---|---|
| 复合条件 `and`/`or`/`not`、字符串比较 | **早就支持** | `runtime.py:207 eval_cond` 走 `eval(expr, SAFE_BUILTINS, env)`，运算符/关键字直接生效 |
| 编辑器实时预览（#9） | **已落地** | `launcher.py:1280 run_preview` + `_preview.stm` 拉起引擎 |
| 编辑器素材面板（#10） | **已落地** | `launcher.py:1350` 素材树 + 双击插入 |
| 状态快照存档 / 快速存读 / 缩略图 | 第 2 期已完成 | 工作记忆确认 |
| 立绘补间 / AutoVoice / include / Call·Return·Repeat·While / doctor / patch / T6 网页版 | 第 2 期已完成 | 同上 |

> 结论：玩家可见功能这一层已经很厚。**第 3 期的方向是「创作者工具链加固」+「演出深度」+「分发广度」**。

## 现有功能清单（成熟度，刷新）

| 功能 | 成熟度 | 说明 |
|---|---|---|
| 剧本语法（含复合条件、include、子程序、循环） | polished | `parser.py` / `runtime.py` |
| 多立绘 + 补间动画 | polished | 移动/淡入/scale/alpha/rotate，带 `dur=` |
| 三通道音频 + 淡入淡出 + 播放列表 | functional | `audio.py`，flac 看 SDL 版本 |
| 转场（fade/dissolve/flash） | functional | `render.py`，种类偏少 |
| 成就 + CG 回廊 + i18n | functional | 跨会话持久化 |
| 快照存档 + 快速存读 + 缩略图 + 导入导出 | polished | `save.py` |
| 网页版（真引擎 wasm / 内置 js，含 R.api 与 stm.os 沙箱） | functional | `web_bridge.py` / `webplayer.html` |
| 在线制作器 webmaker（三栏 IDE + 实时预览） | functional | `webmaker/` + `build_maker.py` |
| 美化包系统（三线硬限制 + 静态校验） | polished | `mod.py` + `modcheck`/`modpub` |
| 打包 / 发布 HTML / Ren'Py 双向转换 / 增量更新 | polished | `tools/` |
| 启动器（CustomTkinter，含编辑器+素材面板+预览） | polished | `launcher.py` |
| 引擎自检 `selftest.py`（90+ 断言） | polished | 无 CI 承载、无 pytest 单测 |

## 功能建议（按优先级排序）

优先级分 = Impact×3 + (4−Effort)×2；Effort：低=1 / 中=2 / 高=3；Impact：低=1 / 中=2 / 高=3。

### 🟢 快速见效（低投入，优先做）

| 功能 | 分类 | 投入 | 回报 | 分 |
|---|---|---|---|---|
| 创作者调试覆盖层（实时变量/标签/事件流/帧率） | 开发者体验 | 低 | 高 | 15 |
| GitHub Actions CI（push 跑 selftest + check） | 开发者体验 | 低 | 中 | 12 |
| 语音重播按钮 `replay_voice` | 功能扩展 | 低 | 中 | 12 |
| pytest 单元测试套件 + 覆盖率 | 开发者体验 | 低 | 中 | 12 |
| Question 输入增强（数字/整数/长度校验） | 功能扩展 | 低 | 中 | 12 |
| 转场特效扩充（滑动/百叶窗/缩放/光圈） | 功能扩展 | 低 | 中 | 12 |

### 🟡 值得投入（中投入，规划做）

| 功能 | 分类 | 投入 | 回报 | 分 |
|---|---|---|---|---|
| 镜头演出 `S.camera(shake/zoom/pan)` | 功能扩展 | 中 | 中 | 10 |
| 素材工作流（批量导入 + Pillow 自动缩放/压缩） | 开发者体验 | 中 | 中 | 10 |
| 美化包在线索引 + 一键安装 | 集成/生态 | 中 | 中 | 10 |
| 章节 / 场景选择菜单（跳 label） | 用户体验 | 中 | 中 | 10 |
| 网页版移动端触屏适配 + PWA 离线安装 | 集成/生态 | 中 | 中 | 10 |
| 键位自定义设置 | 用户体验 | 中 | 中 | 10 |
| 全局持久化存储 `STM.PERSIST`（跨周目通用） | 功能扩展 | 中 | 中 | 10 |
| 导出为视频 / GIF 录屏 | 集成/生态 | 中 | 中 | 10 |

### 🔵 长远目标（高投入，列入路线图）

| 功能 | 分类 | 投入 | 回报 | 分 |
|---|---|---|---|---|
| 移动端 Android 打包（WebView 套壳 + wasm 引擎） | 集成/生态 | 高 | 高 | 11 |

---

## 每个建议的详细说明

### 1. 创作者调试覆盖层（最高优先级）
- **描述**：开发模式现在只把「语法错误」弹成游戏内错误界面（`errors.py` + `gui.py:972`），但写剧本时最想要的是**实时看到当前跑到哪个 label、所有变量的值、`STM.ANSWER`/已选选项、事件流指针**——现在这些全藏在内存里，调试只能靠 `STM.python` 打 toast 或重读源码。
- **实现方案**：`dev_mode=True` 时，在 `gui.draw_advance` 角落叠一个半透明面板：从 `session.runtime` 取 `vars` / 当前 label 名（`runtime._labels` 反查）/ `say_count` / 最近 N 条事件类型；加一个快捷键（`~` 或 `` ` ``）开关。纯展示，不进存档、发布版不渲染。
- **风险/前置**：只读 `runtime` 内部状态，注意别把内部字段名当公开 API 长期依赖；用 `getattr` 容错。

### 2. GitHub Actions CI
- **描述**：`tools/selftest.py` 有 90+ 断言、`tools/check.py` 能查语法和素材，但**全靠本机手动跑**，仓库里没有 `.github/`。引擎改坏只有自己知道。
- **实现方案**：`.github/workflows/ci.yml`：`ubuntu-latest` + Python 3.10/3.12 矩阵，`pip install -r requirements.txt`（pygame 装 `pygame-ce`，设 `SDL_VIDEODRIVER=dummy` + `xvfb`），跑 `python tools/selftest.py` 与 `python tools/check.py demo`。`launcher` 相关的 CTk 测试用 `continue-on-error` 隔离。
- **风险/前置**：无头 pygame 需要 `SDL_VIDEODRIVER=dummy`，selftest 里已有「界面跑一帧」用例正好验证。

### 3. 语音重播按钮 `replay_voice`
- **描述**：`gui.py:1267` 注释明确写着「重听最后一句语音（第 2 期 #10，T5 提供 replay_voice；**未实现**就提示，不崩）」。`AutoVoice` 自动挂载已落地，但 galgame 标配的「重听上一句语音」按钮还没接。
- **实现方案**：`audio.py` 记录最后一次 `voice` 路径；菜单或文本框角加「重听」按钮调 `play_voice(last)`；存档重放时复用 `runtime.quiet` 避免整段重播（`runtime.py` 已有静音机制）。
- **风险/前置**：极低；纯增量。

### 4. pytest 单元测试套件 + 覆盖率
- **描述**：`selftest.py` 是「跑一遍引擎看不报错」式的集成自检，没有针对 `parser`/`runtime`/`save`/`crypto` 的**单元断言**，重构时没有「改这一行会动哪些」的护城河。
- **实现方案**：`tests/` 下按模块建 `test_parser.py` / `test_runtime.py` / `test_save.py` / `test_crypto.py`，用例覆盖：缩进分支判定、复合条件求值、快照存取往返、`.stmdec` 改一字节校验失败。`pip install pytest pytest-cov`，CI 里加 `--cov=stmg`。
- **风险/前置**：`parser`/`runtime` 目前是「喂整段剧本」式调用，需要确认能单独实例化；优先从已有 selftest 用例里抽。

### 5. Question 输入增强（数字 / 整数 / 长度校验）
- **描述**：`runtime.py:322` 的 `question` 事件只收纯文本进 `STM.ANSWER`。做数值输入（年龄/金额）、限长输入时没有原生手段，只能后面用 `SET` 自己 try/转换，体验差。
- **实现方案**：`STM.Q` 之外加 `STM.QTYPE`（"text"/"int"/"num"）和 `STM.QVALID`（如 `min=0,max=120` 或 `len<=10`），`gui.py` 的输入框按类型限制输入并校验，不合法不让确认。网页版 `webplayer.html` 的 question 分支同步。
- **风险/前置**：向后兼容——不写 `QTYPE` 就是现在的纯文本行为。

### 6. 转场特效扩充
- **描述**：`render.py` 现在只有 fade / dissolve / flash（`runtime.py:341`）。推近/百叶窗/缩放/光圈这类演出向转场在商业 galgame 里很常见，现在是空白。
- **实现方案**：`runtime` 的转场事件加 `kind` 字段枚举；`render` 在 offscreen surface 上实现 `slide` / `wipe` / `zoom` / `iris` 几种插值（复用补间插值器）。语法上 `S.cg("x.png", trans="wipe")`。
- **风险/前置**：offscreen 渲染有开销，无转场时走原路径分支，不能拖慢常态帧率。

### 7. 镜头演出 `S.camera(shake/zoom/pan)`
- **描述**：转场有了，但「画面整体动」的手段只有立绘微动。高潮震屏、`S.camera(zoom=1.2, dur=0.5)` 推近、横移看全景，都是成本不高、演出收益明显的语法。确认 `stmg/` 全树无 `S.camera` 实现。
- **实现方案**：runtime 产出 `camera` 事件（`shake`/`zoom`/`pan`），`gui.draw_scene` 在绘制前对整个场景 surface 做偏移/缩放（先渲染到 offscreen 再 blit 变换），复用第 6 条的插值器。
- **风险/前置**：缩放后要处理黑边填充；`stm.os`/存档要存「演出终态」而非插值中间态。

### 8. 素材工作流（批量导入 + 自动缩放/压缩）
- **描述**：启动器素材面板（`launcher.py:1350`）只能「浏览 + 双击插入」，没有「批量导入」「超尺寸图自动缩放」「透明 PNG 转 WebP」。**一张 4000px 背景图会让加载和网页版体积失控**。
- **实现方案**：启动器加「导入素材」批量复制 + 按类型归目录（`project.ASSET_DIRS`）；可选依赖 Pillow：超基准分辨率 1.5 倍的图自动缩、透明 PNG 转 WebP，输出「素材优化报告.md」；`check.py` 结果导出成文件。
- **风险/前置**：Pillow 是可选依赖（缺了就跳过优化并提示）；自动转换**绝不覆盖原文件**，新目录产出。

### 9. 美化包在线索引 + 一键安装
- **描述**：`mod.py`（`grep` 确认）只有静态校验，没有远端 `mods.json` 索引、没有下载安装路径。装包还是「自己解压到 mod/」。
- **实现方案**：约定远端 `mods.json`（`{id,name,author,version,zip_url,sha256,preview}`）；启动器「美化包」对话框加「在线索引」页，拉取 → 校验 sha256 → 解压到 `mod/`；装完复用 `mod.verify` 做静态校验。
- **风险/前置**：⚠️ 唯一会「下载别人文件」的功能，必须强制走 `verify`（现有三条限制正好是安全网）；索引地址写死 HTTPS，避免任意源。

### 10. 章节 / 场景选择菜单
- **描述**：长篇游戏（多 `include` 章节）现在没有「从标题界面跳到第 N 章 / 某个 label」的菜单。玩家想重温某段只能从头快进。`runtime._labels` 已经有全量 label 表，只差一个 UI。
- **实现方案**：标题界面加「章节选择」入口，列出剧本里所有 `label`（可加 `Chapter` 元标签分组），点选 → `S.jump`；配合快照存档可以把「已解锁章节」存进存档，未通关不开放。
- **风险/前置**：label 名可能含 spoiler，提供「只列显式 `@chapter` 标记」的选项。

### 11. 网页版移动端触屏适配 + PWA 离线安装
- **描述**：`webplayer.html` 现在能跑，但没做移动端触屏优化（点击区小、无手势快进），也没 PWA manifest，不能「加到主屏离线玩」。
- **实现方案**：`webplayer.html` 加 viewport + 触摸事件（tap=推进、长按=快进、左滑=历史）；加 `manifest.webmanifest` + Service Worker 缓存 `pyodide/` 与 `assets/`，`htmlpub.py` 一并产出。
- **风险/前置**：Service Worker 缓存 13MB wasm 首次慢，但之后离线；`file://` 下 SW 不生效（已有 wasm 限制，需提示）。

### 12. 键位自定义设置
- **描述**：操作键写死在 `gui.py`（空格/回车推进、`H` 历史、`A` 自动、`Ctrl` 快进、`F5/F9` 存读、`F11` 全屏、`Esc` 菜单）。左撇子 / 外设玩家没法改。
- **实现方案**：`uiconf.DEFAULTS` 加 `keymap` 字典，`Settings` 提供「按键设置」界面，捕获按键写入；`gui` 的 `keydown` 走查表而非硬编码字面量。
- **风险/前置**：网页版 `webplayer.html` 的键位映射要同步一套；冲突键（如和输入法）要做去重。

### 13. 全局持久化存储 `STM.PERSIST`
- **描述**：成就 + CG 回廊已经是跨会话持久化，但没有「通用持久层」。想做「已通关路线」「二周目 flag」「全游戏收集进度」这类跨存档数据，现在只能硬塞进成就系统。
- **实现方案**：`session` 维护一份随引擎配置目录落盘的 `persist.json`，剧本里 `SET STM.PERSIST["route_a"] = true` 即可跨周目读；读档不覆盖 persist（它独立于存档槽）。
- **风险/前置**：persist 与存档的边界要写清——persist 是「玩家这台机器上的进度」，存档是「某一局的快照」。

### 14. 导出为视频 / GIF 录屏
- **描述**：做宣发（B 站 / Steam  trailer）时，现在只能靠 OBS 录屏。引擎内部每一帧都是 pygame surface，天然能截。
- **实现方案**：启动器 / `tools/` 加「录制」模式：推进时对主 surface `pygame.image.tostring` 攒帧，`imageio`（可选依赖）编码成 mp4 / gif；或导出成一系列 PNG 序列交给 ffmpeg。
- **风险/前置**：编码依赖可选（imageio-ffmpeg / ffmpeg），缺了就只出 PNG 序列并提示；录制态要关打字机或加速，避免成品一半是打字过程。

### 15. 移动端 Android 打包
- **描述**：`Pack=` 字段至今注着「留给以后上手机」。引擎架构友好——`Runtime` + `Session` 完全不依赖 pygame，换掉渲染层就能上移动端。
- **实现方案**：Android 优先，复用**网页版**那套 `webplayer.html` + wasm 引擎，用 WebView 套壳（Capacitor / 原生 WebView）打包成 apk；触屏交互复用第 11 条。`stm.os` 在手机上语义改成 App 沙箱目录。
- **风险/前置**：高投入；首次 wasm 加载体积与速度是硬伤（要先做第 11 条的 PWA 缓存）；`R.api` 在移动端照样受 CORS 限制。

---

## 总结建议

第 2 期把「玩家可见功能」铺满了，第 3 期的主线是三件事：

1. **创作者工具链加固**（#1 调试覆盖层、#2 CI、#4 单测、#8 素材工作流）——写长篇、多人协作、改引擎不出事，这几条性价比最高。**先做 #1（调试覆盖层），一天内就能让写剧本的循环变透明。**
2. **演出深度**（#6 转场扩充、#7 镜头演出）——让画面「动起来」的手段补满，质感立刻上一个台阶。
3. **分发广度**（#9 美化包索引、#11 网页移动端 + PWA、#15 安卓）——把「写一次、到处跑」从口号变成真能装进手机。

如果只动一件：**先做 #1（创作者调试覆盖层）**——零风险、纯展示、立刻提升写剧本和改引擎的体感；紧接着做 #2（CI）把「改坏引擎自己不知道」的雷拆掉。

> 想动手的话，告诉我编号，我从改动最小、风险最低的那条开始。
