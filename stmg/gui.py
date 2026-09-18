# -*- coding: utf-8 -*-
"""STMG 主界面（pygame）。

界面状态：标题 / 对白 / 选择支 / 询问输入 / 菜单 / 历史 / 存读档 / 报错 / 结束 / 等待
（等待 = python 代码块逐行飘提示的间隔，到点自己往下走，点一下可以跳过）
渲染统一画在一张 base 画布上，再整体缩放到窗口，所以剧本写多大分辨率都能跑。
"""

import json
import os

import pygame

from . import render, save as savemod, uiconf
from .audio import Audio
from .errors import format_exception
from .session import Session

(TITLE, ADVANCE, CHOOSE, QUESTION, MENU, BACKLOG, SAVELOAD, ERROR, ENDING,
 GALLERY, WAIT) = range(11)

# 设置面板里「字体」可循环切换的候选（"" = 用剧本头部的 Font=）
FONT_CHOICES = ["", "微软雅黑", "黑体", "宋体", "楷体"]

# 界面尺寸、颜色、位置全在 uiconf.DEFAULTS 里，
# 项目目录下的 custom/gui.py 可以覆盖任意一项——别在这里写死数值。


class Settings(object):
    def __init__(self, root):
        self.root = root
        self.path = os.path.join(root, ".stmg_save", "settings.json")
        self.text_speed = 45.0     # 每秒显示多少字，<0 表示瞬间全出
        self.auto_delay = 1.6
        self.vol = {"bgm": 0.7, "se": 0.8, "voice": 1.0}
        self.fullscreen = False
        # ---- 第 2 期新增的显示 / 排版设置（缺省值保持老行为）----
        self.font_scale = 1.0       # 正文字号倍率 0.8~1.6
        self.line_spacing = 1.45    # 行距 1.2~2.0
        self.box_alpha = None       # 文本框透明度；None = 用 uiconf 的默认值
        self.typewriter = True      # False = 文字瞬间全出
        self.font_name = ""         # 界面字体；"" = 用剧本头部的 Font=
        self.quick_slot = 1         # 快速存读用的槽位（F5/F9）
        self.load()

    def load(self):
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self.text_speed = d.get("text_speed", self.text_speed)
                self.auto_delay = d.get("auto_delay", self.auto_delay)
                self.vol.update(d.get("vol", {}))
                self.fullscreen = bool(d.get("fullscreen", False))
                self.font_scale = float(d.get("font_scale", self.font_scale))
                self.line_spacing = float(d.get("line_spacing", self.line_spacing))
                if "box_alpha" in d:                 # 0 是合法值，不能用 d.get 的默认值
                    self.box_alpha = d["box_alpha"]
                self.typewriter = bool(d.get("typewriter", self.typewriter))
                self.font_name = d.get("font_name", self.font_name) or ""
                self.quick_slot = int(d.get("quick_slot", self.quick_slot))
            except (ValueError, OSError):
                pass

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"text_speed": self.text_speed,
                           "auto_delay": self.auto_delay,
                           "vol": self.vol,
                           "fullscreen": self.fullscreen,
                           "font_scale": self.font_scale,
                           "line_spacing": self.line_spacing,
                           "box_alpha": self.box_alpha,
                           "typewriter": self.typewriter,
                           "font_name": self.font_name,
                           "quick_slot": self.quick_slot}, f, indent=1)
        except OSError:
            pass


class App(object):
    def __init__(self, script, options=None, dev_mode=True, auto=False,
                 script_errors=None, mod_id=None, no_mod=False):
        pygame.init()
        self.script = script
        self.dev_mode = dev_mode
        self.root = os.path.dirname(os.path.abspath(script.path))
        self.W, self.H = script.size
        self.settings = Settings(self.root)
        # 界面外观三层叠加：引擎默认值 < 美化包（mod/） < custom/gui.py
        self.ui, self.ui_error = uiconf.setup(self.root, mod_id, no_mod)

        self._open_window()
        self.base = pygame.Surface((self.W, self.H)).convert()

        self.fonts = render.FontSet(render.find_font_file(
            self.settings.font_name or script.font))
        self.audio = Audio()
        for k, v in self.settings.vol.items():
            self.audio.set_volume(k, v)

        # 解析期错误：在游戏窗口里显示（Ren'Py 风格），而不是丢到命令行
        self.script_errors = list(script_errors) if script_errors else []
        self.error_mode = "script" if self.script_errors else "runtime"
        self.error_scroll = 0

        self.session = None
        self.error_text = ""
        try:
            self.session = Session(script, options, dev_mode)
        except Exception as e:                       # noqa: BLE001
            self.error_text = "引擎初始化失败：%s\n%s" % (e, format_exception(e))

        self.state = TITLE
        self.buttons = []
        self.reveal = 0.0
        self.auto = auto
        self.skip = False
        self.auto_timer = 0.0
        self.wait_timer = 0.0          # python 代码块的等待：已经等了几秒
        self.wait_dur = 0.0            # 还要等几秒（到点自动往下走）
        self.achieve_popups = []       # 成就解锁弹窗（update/draw 都会读它）
        self.input_text = ""
        self.backlog_scroll = 0
        self.overlay_from = TITLE
        self.pending_toasts = []
        self.running = True

        # ---- 第 2 期：补间动画状态 ----
        self.anim = {}              # tag / 键 -> 补间动画字典
        self._prev_scene = None    # 推进前的场景快照，用作补间的起点

        # ---- 玩家体验相关状态（默认均不影响原有行为）----
        self.transition = None          # 转场动画：{"kind","dur","t"} 或 None
        self._prev_frame = None         # 转场用：上一帧快照
        self.seen = set()               # 已经「看过」的台词 (who, text)，供快进跳过
        self._shown_chars = 0           # 打字机音效：上一帧已经显示出来的字数
        self.skip_read = bool(self.ui.get("skip_read", True))
        self.type_se = self.ui.get("type_se", "") or ""
        self.type_se_volume = float(self.ui.get("type_se_volume", 0.5))

        # 项目自定义界面出问题的话，开发模式下提示一句（不影响游戏）
        if self.ui_error and self.dev_mode:
            self.pending_toasts.append("界面配置：" + self.ui_error)

        # ---- 多语言：script.stm 为默认版，script.<lang>.stm 是其它语言 ----
        # 标题界面会出现「语言」按钮循环切换；选择记在 .stmg_save/lang.json。
        # 换语言只换剧本文件，窗口大小沿用首次加载的分辨率。
        self.langs = {}            # {语言标记: 路径}
        self.lang_order = []       # 切换用的稳定顺序
        self.current_lang = ""
        try:
            from . import project as _proj
            self.langs = _proj.find_languages(script.path)
            self.lang_order = sorted(self.langs.keys())
            saved = savemod.load_lang(self.root, os.path.basename(self.root))
            if saved != "" and saved in self.langs and \
                    os.path.normcase(self.langs[saved]) != \
                    os.path.normcase(script.path):
                self._apply_lang(saved, silent=True)
        except Exception:                          # noqa: BLE001
            self.langs, self.lang_order = {}, []

        # 标题界面的 BGM（项目 custom/gui.py 里配的 title_bgm）
        self._title_bgm_on()

        # 有解析错误：直接进错误界面，窗口照开，但不进标题 / 游戏
        if self.script_errors:
            self.state = ERROR

    # ------------------------------------------------------------------ #
    # 窗口
    # ------------------------------------------------------------------ #
    def _open_window(self):
        info = pygame.display.Info()
        max_w, max_h = int(info.current_w * 0.9), int(info.current_h * 0.9)
        self.scale = min(1.0, max_w / float(self.W), max_h / float(self.H))
        size = (int(self.W * self.scale), int(self.H * self.scale))
        flags = pygame.FULLSCREEN if self.settings.fullscreen else 0
        self.screen = pygame.display.set_mode(size, flags)
        pygame.display.set_caption(self.script.title)

    def _to_base(self, pos):
        return (int(pos[0] / self.scale), int(pos[1] / self.scale))

    def draw_buttons(self, size):
        """统一画按钮。鼠标位置得换算回 base 坐标，不然放大/缩小时高亮会偏。"""
        mouse = self._to_base(pygame.mouse.get_pos())
        for b in self.buttons:
            b.draw(self.base, self.fonts, size, mouse)

    # ------------------------------------------------------------------ #
    # 资源
    # ------------------------------------------------------------------ #
    def asset(self, *parts):
        p = os.path.join(self.root, "gui", *parts)
        return p if os.path.isfile(p) else ""

    def ui_path(self, name):
        """custom/gui.py 里写的资源路径 → 绝对路径（不存在就返回空串）。"""
        if not name:
            return ""
        p = str(name).replace("\\", "/")
        if os.path.isabs(p):
            return p if os.path.isfile(p) else ""
        full = os.path.join(self.root, p)
        return full if os.path.isfile(full) else ""

    def _title_bgm_on(self):
        path = self.ui_path(self.ui.get("title_bgm"))
        if not path:
            return
        self.audio.set_volume("bgm", self.ui.get("title_bgm_volume",
                                                 self.settings.vol["bgm"]))
        self.audio.apply({"t": "bgm", "path": path, "loop": True})

    def box_rect(self):
        """对话框矩形——位置和大小由项目里的 custom/gui.py 决定。"""
        u = self.ui
        h = int(self.H * u["box_h"])
        w = int(self.W * u["box_w"])
        x = int(self.W * u["box_x"])
        y = self.H - h - int(self.H * u["box_y"])
        return pygame.Rect(x, y, w, h)

    def apply_effects(self):
        for ev in self.session.effects:
            self.audio.apply(ev)
            if ev["t"] == "achieve" and ev.get("is_new"):
                # 只有「第一次解锁」才弹窗（runtime 已经过滤过，这里再保险一次）
                self.achieve_popups.append({
                    "name": ev.get("name", ""),
                    "ttl": float(self.ui.get("achieve_popup_dur", 3.0)),
                })
            # ---- 第 2 期 #2：立绘 / 背景 / 叠图带上 dur 时平滑过渡，而不是瞬切 ----
            elif ev["t"] == "sprite" and ev.get("dur"):
                self._setup_anim("sprite", ev.get("tag") or "_", ev["dur"])
            elif ev["t"] == "bg" and ev.get("dur"):
                self._setup_anim("bg", "_bg", ev["dur"])
            elif ev["t"] == "picture" and ev.get("dur"):
                self._setup_anim("picture", "_pic", ev["dur"])
        if self.session.toasts:
            self.pending_toasts.extend(self.session.toasts)

    # ------------------------------------------------------------------ #
    # 补间动画（第 2 期 #2）
    # ------------------------------------------------------------------ #
    def _capture_scene(self):
        """推进前先快照当前场景，作为补间的起点。"""
        sc = self.session.scene
        return {
            "bg": sc.get("bg", ""),
            "picture": sc.get("picture", ""),
            "sprites": {t: dict(v) for t, v in (sc.get("sprites") or {}).items()},
        }

    def _setup_anim(self, kind, key, dur):
        """为一个 sprite/bg/picture 建立补间：from=起点，to=当前场景终态。"""
        if self._prev_scene is None:
            return                          # 读档 / 开局等没有起点，直接落终态
        if self.skip:
            self.anim.pop(key, None)        # 快进 / 跳过：直接到终态
            return
        if kind == "sprite":
            to = dict(self.session.scene.get("sprites", {}).get(key, {}))
            fr = dict(self._prev_scene["sprites"].get(key, to))
        elif kind == "bg":
            to = {"path": self.session.scene.get("bg", "")}
            fr = {"path": self._prev_scene.get("bg", "")}
        else:                               # picture
            to = {"path": self.session.scene.get("picture", "")}
            fr = {"path": self._prev_scene.get("picture", "")}
        self.anim[key] = {"kind": kind, "from": fr, "to": to,
                          "t": 0.0, "dur": max(0.0, float(dur))}

    @staticmethod
    def _anim_p(a):
        if a["dur"] <= 0:
            return 1.0
        return min(1.0, a["t"] / a["dur"])

    def _sprite_cx(self, item):
        """立绘水平中心 x（像素）；补间时用插值后的 _xfrac，否则按 pos 映射。"""
        xfr = item.get("_xfrac")
        if xfr is None:
            xfr = self.ui["sprite_x"].get(item.get("pos", "center"), 0.5)
        return int(self.W * xfr)

    # ------------------------------------------------------------------ #
    # 主循环
    # ------------------------------------------------------------------ #
    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            dt = clock.tick(60) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()
            pygame.display.flip()
        self.settings.save()
        self.audio.shutdown()
        pygame.quit()

    def update(self, dt):
        # 音频淡入淡出驱动（第 2 期 #5，T5 提供 update；没实现就跳过，保证不崩）
        au = getattr(self.audio, "update", None)
        if callable(au):
            try:
                au(dt)
            except Exception:                              # noqa: BLE001
                pass

        # 转场动画独立于台词推进，每帧累加时间，到时结束
        if self.transition:
            self.transition["t"] += dt
            if self.transition["t"] >= self.transition["dur"]:
                self.transition = None
                self._prev_frame = None

        # 补间动画：每帧推进，到时删掉（场景已是终态）；快进直接落终态
        if self.anim:
            if self.skip:
                self.anim.clear()
            else:
                for a in self.anim.values():
                    if a["dur"] > 0:
                        a["t"] += dt
                for k in [k for k in self.anim
                          if self.anim[k]["dur"] <= 0
                          or self.anim[k]["t"] >= self.anim[k]["dur"]]:
                    del self.anim[k]

        # python 代码块的逐行提示：等够 dur 秒就自动推进（点一下可以提前跳过）
        if self.state == WAIT:
            self.wait_timer += dt
            if self.wait_timer >= max(0.0, self.wait_dur):
                self.wait_timer = 0.0
                self.wait_dur = 0.0
                self.session.next_block()
                self.apply_effects()
                self.sync_state()

        if self.state in (ADVANCE, CHOOSE, QUESTION):
            # 第 2 期：关掉打字机、或文字速度为负，都让文字瞬间全出
            if self.settings.text_speed < 0 or not self.settings.typewriter:
                self.reveal = 1e9
            else:
                self.reveal += self.settings.text_speed * dt
            if self.state == ADVANCE:
                if self.skip and self.skip_read:
                    # 快进（Ctrl）：只自动跳过「已经看过」的台词，
                    # 遇到没看过的台词或选择/问答就停下来让人看。
                    blk = self.session.block
                    if blk and blk["t"] == "say" and \
                            (blk.get("who"), blk.get("text")) in self.seen:
                        self.reveal = 1e9
                        self.advance()
                elif self.skip:
                    # skip_read 关掉时，行为和原来一样：露出就往前走
                    if self.is_revealed():
                        self.advance()
                elif self.auto:
                    if self.is_revealed():
                        self.auto_timer += dt
                        if self.auto_timer >= self.settings.auto_delay:
                            self.auto_timer = 0
                            self.advance()

                # 打字机每字音效：每多显示出一个字就响一下
                if self.type_se and self.settings.text_speed >= 0:
                    total = self._total_chars()
                    cur = int(min(self.reveal, total))
                    if cur < total and cur > self._shown_chars:
                        self._shown_chars = cur
                        self.audio.play_se_once(self.type_se, self.type_se_volume)
                    elif cur >= total:
                        self._shown_chars = total

        # 成就解锁弹窗倒计时
        if self.achieve_popups:
            for p in self.achieve_popups:
                p["ttl"] -= dt
            self.achieve_popups = [p for p in self.achieve_popups if p["ttl"] > 0]

    def is_revealed(self):
        return self.reveal >= self._total_chars()

    def _total_chars(self):
        return len(self.session.text)

    # ------------------------------------------------------------------ #
    def advance(self):
        if self.state != ADVANCE:
            return
        self._prev_scene = self._capture_scene()
        blk = self.session.block
        if blk and blk["t"] == "say":
            # 玩家把这句推过去，说明读过了，下次快进可以跳过
            self.seen.add((blk.get("who"), blk.get("text")))
        self.reveal = 0.0
        self.auto_timer = 0.0
        self._shown_chars = 0
        self.session.next_block()
        self.apply_effects()
        self.sync_state()

    def choose(self, index):
        self._prev_scene = self._capture_scene()
        self.reveal = 0.0
        self._shown_chars = 0
        self.session.answer(self.session.block["options"][index])
        self.apply_effects()
        self.sync_state()

    def submit_answer(self, text):
        self._prev_scene = self._capture_scene()
        self.reveal = 0.0
        self._shown_chars = 0
        self.session.answer(text)
        self.apply_effects()
        self.sync_state()

    def sync_state(self):
        blk = self.session.block
        t = blk["t"]
        if t == "transition":
            # 转场事件：先把上一帧快照下来，再去拿紧跟在后面的真实内容
            # （背景切换 / 下一句台词），转场遮罩会在 draw 里跨这两帧渐变。
            self._start_transition(blk)
            self.session.next_block()
            self.apply_effects()
            self.sync_state()
            return
        if t == "wait":
            # python 代码块：这一行的提示刚飘出来，先亮一会儿再显示下一行。
            # reveal 拉满，让对话框继续完整显示上一句台词。
            self.wait_dur = float(blk.get("dur") or 0.0)
            self.wait_timer = 0.0
            self.reveal = 1e9
            self.state = WAIT
        elif t == "say":
            self.state = ADVANCE
        elif t == "choose":
            self.state = CHOOSE
        elif t == "question":
            self.state = QUESTION
            self.input_text = ""
            pygame.key.start_text_input()
        elif t == "fatal":
            self.error_text = blk.get("message", "") + "\n" + blk.get("trace", "")
            self.state = ERROR
        else:
            self.state = ENDING

    def _start_transition(self, blk):
        """记下转场参数，并快照「当前画面」作为渐变的起点帧。"""
        kind = blk.get("kind") or self.ui.get("transition_default") or "fade"
        dur = blk.get("dur")
        if dur in (None, ""):
            dur = self.ui.get("transition_dur", 0.4)
        try:
            dur = float(dur)
        except (TypeError, ValueError):
            dur = 0.4
        self._prev_frame = self.base.copy() if self.base is not None else None
        self.transition = {"kind": kind, "dur": max(0.001, dur), "t": 0.0}

    # ------------------------------------------------------------------ #
    # 事件
    # ------------------------------------------------------------------ #
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                continue

            if event.type == pygame.KEYDOWN:
                self.on_key(event)
            elif event.type == pygame.KEYUP:
                self._key_release(event)

            if self.state == QUESTION and event.type == pygame.TEXTINPUT:
                if len(self.input_text) < 60:
                    self.input_text += event.text
                continue

            if self.state in (TITLE, MENU, SAVELOAD, BACKLOG, ENDING, ERROR,
                              GALLERY):
                for b in self.buttons:
                    act = b.handle(event)
                    if act:
                        act()
                        break
                if event.type == pygame.MOUSEBUTTONDOWN and self.state == GALLERY \
                        and getattr(self, "gallery_view", ""):
                    self.gallery_view = ""      # 放大查看时点一下就回画廊
                if event.type == pygame.MOUSEBUTTONDOWN and self.state == BACKLOG:
                    self.backlog_scroll += -3 if event.button == 4 else 3 if event.button == 5 else 0
                    self.backlog_scroll = max(0, min(self.backlog_scroll,
                                                     max(0, len(self.session.runtime.history) - 6)))
                if event.type == pygame.MOUSEWHEEL and self.state == ERROR \
                        and self.error_mode == "script":
                    self.error_scroll = max(0, self.error_scroll - event.y * 3)
                continue

            if self.state == WAIT:
                # 等 python 代码块的下一行时，点一下 / 按一下就直接跳过剩下的等待
                if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                    self.wait_timer = 1e9
                continue

            if self.state == CHOOSE:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    p = self._to_base(event.pos)
                    for i, r in enumerate(self.choice_rects()):
                        if r.collidepoint(p):
                            self.choose(i)
                            break
                continue

            if self.state == ADVANCE:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.is_revealed():
                        self.advance()
                    else:
                        self.reveal = 1e9
                elif event.type == pygame.MOUSEWHEEL and event.y > 0:
                    self.open_backlog()

    def on_key(self, event):
        k = event.key
        # 解析错误界面：回车 / Esc 直接关窗口（没有可继续的游戏）
        if self.state == ERROR and self.error_mode == "script":
            if k in (pygame.K_RETURN, pygame.K_ESCAPE):
                self.running = False
            return
        if k == pygame.K_ESCAPE:
            if self.state in (MENU, BACKLOG, SAVELOAD, GALLERY):
                self.state = self.overlay_from
                self.about_only = False
                self.buttons = []
            else:
                self.open_menu()
            return
        if k == pygame.K_F11:
            self.toggle_fullscreen()
            return
        if self.state == QUESTION:
            if k == pygame.K_BACKSPACE:
                self.input_text = self.input_text[:-1]
            elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.submit_answer(self.input_text)
            return
        if self.state == ADVANCE:
            if k in (pygame.K_SPACE, pygame.K_RETURN):
                if self.is_revealed():
                    self.advance()
                else:
                    self.reveal = 1e9
            elif k == pygame.K_h:
                self.open_backlog()
            elif k == pygame.K_a:
                self.auto = not self.auto
            elif k in (pygame.K_LCTRL, pygame.K_RCTRL):
                self.skip = True
            elif k == pygame.K_F5:
                # Shift+F5 开存读档界面；否则快速存到上次用的槽（没有就槽 1）
                if event.mod & pygame.KMOD_SHIFT:
                    self.open_saveload(True)
                else:
                    self.quick_save()
            elif k == pygame.K_F9:
                if event.mod & pygame.KMOD_SHIFT:
                    self.open_saveload(False)
                else:
                    self.quick_load()
        elif self.state == ENDING and k in (pygame.K_RETURN, pygame.K_SPACE):
            self.running = False
        elif self.state == ERROR and k == pygame.K_RETURN:
            self.state = ENDING

    def _key_release(self, event):
        if event.key in (pygame.K_LCTRL, pygame.K_RCTRL):
            self.skip = False

    # ------------------------------------------------------------------ #
    # 界面
    # ------------------------------------------------------------------ #
    def open_menu(self):
        self.overlay_from = self.state
        self.state = MENU
        self.about_only = False
        self.buttons = []

    def toggle_fullscreen(self):
        self.settings.fullscreen = not self.settings.fullscreen
        pygame.display.quit()
        pygame.display.init()
        self._open_window()
        # 显示模式重开之后，之前 convert 出来的 surface 都作废了
        render._image_cache.clear()
        self.base = pygame.Surface((self.W, self.H)).convert()
        self.pending_toasts.append("全屏：%s" % ("开" if self.settings.fullscreen else "关"))

    def open_backlog(self):
        self.overlay_from = self.state
        self.state = BACKLOG
        self.backlog_scroll = max(0, len(self.session.runtime.history) - 6)
        self.buttons = []

    def open_saveload(self, saving):
        self.overlay_from = self.state
        self.state = SAVELOAD
        self.save_mode = saving
        self.buttons = []

    def title_buttons(self):
        out = []
        cx = self.W // 2
        y = int(self.H * 0.44)
        labels = [("开始游戏", self.start_game, "start.png"),
                  ("读取存档", lambda: self.open_saveload(False), "")]
        if len(self.lang_order) >= 2:
            labels.append(("语言: %s" % (self.current_lang or "默认"),
                           self.cycle_lang, ""))
        labels += [("CG 回廊", self.open_gallery, ""),
                   ("设置", self.open_menu, "setting.png"),
                   ("关于", self.show_about, "about.png")]
        for i, (label, act, img) in enumerate(labels):
            r = pygame.Rect(cx - 110, y + i * 56, 220, 44)
            pic = self.asset("button", img) if img else ""
            out.append(render.Button(r, label, act,
                                     render.load_image(pic, r.size) if pic else None))
        return out

    def start_game(self):
        # 标题曲到此为止，音量还给玩家设置
        if self.ui.get("title_bgm"):
            self.audio.apply({"t": "stop", "what": "bgm"})
            for k, v in self.settings.vol.items():
                self.audio.set_volume(k, v)
        self._prev_scene = None
        self.anim.clear()
        self.session.reset()
        self.apply_effects()
        self.reveal = 0.0
        self._shown_chars = 0
        self.sync_state()

    def show_about(self):
        self.overlay_from = TITLE
        self.state = MENU
        self.about_only = True

    # ------------------------------------------------------------------ #
    # 多语言切换
    # ------------------------------------------------------------------ #
    def _apply_lang(self, lang, silent=False):
        """把剧本换成对应语言版本；失败返回 False（当前版本不动）。"""
        path = self.langs.get(lang)
        if not path:
            return False
        from . import parser as _parser
        sc = _parser.parse_file(path)
        if sc.error_count():
            if not silent and self.dev_mode:
                self.pending_toasts.append(
                    "语言版本 %s 有 %d 个错误，加载失败" % (lang or "默认",
                                                    sc.error_count()))
            return False
        self.script = sc
        self.current_lang = lang
        self.session = Session(sc, getattr(self.session, "options", None),
                               self.dev_mode)
        # 语言偏好按项目目录记（不同语言版本的 title 应保持一致）
        savemod.save_lang(self.root, os.path.basename(self.root), lang)
        if not silent:
            self.pending_toasts.append("Language: %s" % (lang or "default"))
        return True

    def cycle_lang(self):
        if len(self.lang_order) < 2:
            return
        i = self.lang_order.index(self.current_lang) \
            if self.current_lang in self.lang_order else 0
        self._apply_lang(self.lang_order[(i + 1) % len(self.lang_order)])

    # ------------------------------------------------------------------ #
    # CG 回廊
    # ------------------------------------------------------------------ #
    def open_gallery(self):
        self.overlay_from = TITLE
        self.state = GALLERY
        self.gallery_view = ""
        self.gallery_paths = sorted(getattr(self.session.runtime, "seen_cg", set()))
        self.buttons = []
        cols = 4
        cw, ch = 150, 100
        gap = 18
        x0 = (self.W - cols * cw - (cols - 1) * gap) // 2
        y0 = int(self.H * 0.16)
        for i, p in enumerate(self.gallery_paths):
            col, row = i % cols, i // cols
            r = pygame.Rect(x0 + col * (cw + gap), y0 + row * (ch + gap), cw, ch)
            img = render.load_image(p, r.size)
            if img:
                self.buttons.append(render.Button(r, "", (lambda pp=p: self._view_cg(pp)), img))

    def _view_cg(self, path):
        self.gallery_view = path
        self.buttons = []

    def draw_gallery(self):
        # 深色底 + 网格缩略图；点缩略图放大，Esc 返回标题
        self.base.fill((16, 16, 24))
        title = self.fonts.get(int(self.H * 0.05)).render("CG 回廊", True, (235, 235, 245))
        self.base.blit(title, (self.W // 2 - title.get_width() // 2, int(self.H * 0.05)))
        hint = self.fonts.get(18).render("Esc 返回标题 · 点缩略图放大", True, (150, 150, 170))
        self.base.blit(hint, (self.W // 2 - hint.get_width() // 2, self.H - int(self.H * 0.06)))
        if getattr(self, "gallery_view", ""):
            big = render.load_image(self.gallery_view)
            if big:
                img = render.fit_into(big, int(self.W * 0.92), int(self.H * 0.8))
                self.base.blit(img, ((self.W - img.get_width()) // 2,
                                     (self.H - img.get_height()) // 2))
            return
        if not self.gallery_paths:
            tip = self.fonts.get(22).render("还没有解锁任何 CG——多玩玩就有了喵～",
                                            True, (160, 160, 180))
            self.base.blit(tip, (self.W // 2 - tip.get_width() // 2, self.H // 2))
        else:
            self.draw_buttons(22)

    # ------------------------------------------------------------------ #
    def choice_rects(self):
        opts = self.session.block.get("options", []) if self.session.block else []
        n = len(opts)
        u = self.ui
        w, h, gap = int(self.W * u["choice_w"]), u["choice_h"], u["choice_gap"]
        x = (self.W - w) // 2
        y0 = self.H // 2 - (n * (h + gap)) // 2
        return [pygame.Rect(x, y0 + i * (h + gap), w, h) for i in range(n)]

    def draw(self):
        if self.state == TITLE:
            self.draw_title()
        elif self.state == ERROR:
            self.draw_error()
        elif self.state == GALLERY:
            self.draw_gallery()
        elif self.state == ENDING:
            self.draw_ending()
        else:
            self.draw_scene()
            if self.state == CHOOSE:
                self.draw_choices()
            elif self.state == QUESTION:
                self.draw_question()
            if self.state == MENU:
                self.draw_menu()
            elif self.state == BACKLOG:
                self.draw_backlog()
            elif self.state == SAVELOAD:
                self.draw_saveload()

        # 转场遮罩：盖在场景之上做整屏渐变（fade / dissolve / flash）
        if self.transition and self.state not in (TITLE, ERROR, ENDING):
            dur = self.transition["dur"]
            p = (self.transition["t"] / dur) if dur > 0 else 1.0
            render.draw_transition(self.base, self.transition["kind"], p,
                                   self.W, self.H, (16, 16, 22), self._prev_frame)

        render.draw_toasts(self.base, self.fonts, self.pending_toasts[-4:], self.W,
                           size=self.ui["toast_size"])
        if self.scale != 1.0:
            pygame.transform.smoothscale(self.base, self.screen.get_size(), self.screen)
        else:
            self.screen.blit(self.base, (0, 0))

    # ------------------------------------------------------------------ #
    def draw_title(self):
        u = self.ui
        # 标题背景：配了图就用图，没配就用渐变（两个端点色也能改）
        bg = render.load_image(self.ui_path(u["title_bg"]))
        if bg:
            bg = render.fit_into(bg, self.W, self.H)
            self.base.fill((16, 16, 22))
            self.base.blit(bg, ((self.W - bg.get_width()) // 2,
                                (self.H - bg.get_height()) // 2))
        else:
            top, bottom = u["title_top"], u["title_bottom"]
            for i in range(self.H):
                k = i / float(self.H)
                c = tuple(int(top[j] + (bottom[j] - top[j]) * k) for j in range(3))
                pygame.draw.line(self.base, c, (0, i), (self.W, i))

        banner = self.ui_path(u["title_pic"]) or self.asset("button", "title.png")
        pic = render.load_image(banner)
        if pic:
            pic = render.fit_into(pic, int(self.W * 0.7), int(self.H * 0.3))
            self.base.blit(pic, ((self.W - pic.get_width()) // 2,
                                 int(self.H * u["title_y"])))
        else:
            f = self.fonts.get(int(self.H * u["title_size"]), bold=True)
            t = f.render(self.script.title, True, (255, 255, 255))
            self.base.blit(t, ((self.W - t.get_width()) // 2,
                               int(self.H * u["title_y"])))
            f2 = self.fonts.get(18)
            sub = f2.render("STMG v%s   |   按 Esc 打开菜单"
                            % self.script.header.get("ver", "1.0.0"),
                            True, (200, 205, 225))
            self.base.blit(sub, ((self.W - sub.get_width()) // 2,
                                 int(self.H * (u["title_y"] + 0.12))))

        self.buttons = self.title_buttons()
        self.draw_buttons(22)

    def draw_scene(self):
        self.base.fill((16, 16, 22))
        # 背景：带 dur 时做交叉淡入（老背景先停着，新背景渐渐显出来）
        bg_path = self.session.scene.get("bg", "")
        a = self.anim.get("_bg")
        if a is not None:
            p = self._anim_p(a)
            old = a["from"].get("path", "")
            oldimg = render.load_image(old) if old else None
            if oldimg:
                oldimg = render.fit_into(oldimg, self.W, self.H)
                self.base.blit(oldimg, ((self.W - oldimg.get_width()) // 2,
                                        (self.H - oldimg.get_height()) // 2))
            self._draw_crossfade(bg_path, p, self.W, self.H, 0.72)
        else:
            bg = render.load_image(bg_path)
            if bg:
                bg = render.fit_into(bg, self.W, self.H)
                self.base.blit(bg, ((self.W - bg.get_width()) // 2,
                                    (self.H - bg.get_height()) // 2))
            else:
                render.draw_placeholder(self.base, pygame.Rect(0, 0, self.W, int(self.H * 0.72)),
                                        bg_path or "背景", 0)

        # 叠图：带 dur 时同样淡入
        pic = self.session.scene.get("picture", "")
        a = self.anim.get("_pic")
        if a is not None:
            p = self._anim_p(a)
            old = a["from"].get("path", "")
            if old:
                oimg = render.load_image(old)
                if oimg:
                    oimg = render.fit_into(oimg, int(self.W * self.ui["pic_w"]),
                                           int(self.H * self.ui["pic_h"]))
                    self.base.blit(oimg, ((self.W - oimg.get_width()) // 2,
                                          int(self.H * self.ui["pic_center_y"])
                                          - oimg.get_height()))
            self._draw_pic(pic, p)
        elif pic:
            self._draw_pic(pic, 1.0)
        else:
            r = pygame.Rect(int(self.W * (0.5 - self.ui["pic_w"] / 2.0)),
                            int(self.H * 0.1), int(self.W * self.ui["pic_w"]),
                            int(self.H * (self.ui["pic_h"] - 0.1)))
            render.draw_placeholder(self.base, r, pic, 2)

        # 立绘：tag -> {path, pos}，可以同时站好几张，按 tag 排序保证叠放稳定
        sprites = self.session.scene.get("sprites") or {}
        u = self.ui
        for i, tag in enumerate(sorted(sprites)):
            item = sprites[tag]
            # 补间进行中：用插值后的 item（水平位置用 _xfrac 表达）
            a = self.anim.get(tag)
            if a is not None:
                item = render.tween_sprite(a["from"], a["to"], self._anim_p(a),
                                           u["sprite_x"],
                                           u.get("sprite_scale_default", 1.0))
            path = item.get("path", "")
            cx = self._sprite_cx(item)
            bottom = int(self.H * u["sprite_bottom"])
            img = render.load_image(path)
            if img:
                render.draw_sprite(self.base, img, cx, bottom, item, u,
                                   self.W, self.H)
            else:
                w, h = int(self.W * 0.2), int(self.H * 0.54)
                r = pygame.Rect(cx - w // 2, bottom - h, w, h)
                render.draw_placeholder(self.base, r, path, i + 1)

        self.draw_textbox()

    def _draw_crossfade(self, path, p, w, h, h_frac):
        """按透明度 p 把图片淡入到全屏（背景补间用，p<1 时半透明）。"""
        img = render.load_image(path)
        if not img:
            render.draw_placeholder(self.base,
                                   pygame.Rect(0, 0, w, int(h * h_frac)),
                                   path or "背景", 0)
            return
        img = render.fit_into(img, w, h)
        surf = img.copy()
        surf.set_alpha(int(255 * p))
        self.base.blit(surf, ((w - surf.get_width()) // 2,
                              (h - surf.get_height()) // 2))

    def _draw_pic(self, path, p):
        """画叠图；p<1 时按透明度淡入（叠图补间用）。"""
        if not path:
            return
        img = render.load_image(path)
        if not img:
            r = pygame.Rect(int(self.W * (0.5 - self.ui["pic_w"] / 2.0)),
                            int(self.H * 0.1), int(self.W * self.ui["pic_w"]),
                            int(self.H * (self.ui["pic_h"] - 0.1)))
            render.draw_placeholder(self.base, r, path, 2)
            return
        img = render.fit_into(img, int(self.W * self.ui["pic_w"]),
                              int(self.H * self.ui["pic_h"]))
        if p < 1.0:
            img = img.copy()
            img.set_alpha(int(255 * p))
        self.base.blit(img, ((self.W - img.get_width()) // 2,
                             int(self.H * self.ui["pic_center_y"]) - img.get_height()))

    def draw_textbox(self):
        u = self.ui
        box = self.box_rect()
        img = render.load_image(self.asset("textbox", "box.png"), box.size)
        if img:
            self.base.blit(img, box)
        else:
            panel = pygame.Surface(box.size, pygame.SRCALPHA)
            c = u["box_color"]
            # 第 2 期：设置里 box_alpha 非 None 时覆盖透明度
            alpha = self.settings.box_alpha
            if alpha is None:
                alpha = u["box_alpha"]
            panel.fill((c[0], c[1], c[2], alpha))
            self.base.blit(panel, box)
            if u["box_border"]:
                pygame.draw.rect(self.base, u["box_border_color"], box,
                                 u["box_border"], border_radius=u["box_radius"])

        who = self.session.speaker
        text = self.session.text
        pad = u["text_pad"]
        y = box.y + pad
        if who:
            f = self.fonts.get(u["name_size"], bold=True)
            t = f.render(who, True, u["name_color"])
            nh = int(self.H * u["name_h"])
            nr = pygame.Rect(box.x + pad, box.y - nh + 12,
                             t.get_width() + 34, nh - 6)
            pygame.draw.rect(self.base, u["name_bg"], nr, border_radius=8)
            self.base.blit(t, (nr.x + 17, nr.centery - t.get_height() // 2))
            y = box.y + pad

        runs = render.md(text)
        # 第 2 期 #8：字号倍率乘到 base_size，行距用设置值
        base = u["text_size"] * self.settings.font_scale
        lines, line_h = render.layout(runs, self.fonts,
                                      box.width - pad * 2,
                                      base_size=base,
                                      line_spacing=self.settings.line_spacing)
        shown = render.reveal(lines, int(self.reveal))
        render.draw_lines(self.base, shown, self.fonts, box.x + pad, y,
                          line_h, base_size=base)

    def draw_choices(self):
        dim = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 90))
        self.base.blit(dim, (0, 0))
        opts = self.session.block.get("options", [])
        for i, r in enumerate(self.choice_rects()):
            mouse = self._to_base(pygame.mouse.get_pos())
            hover = r.collidepoint(mouse)
            bg = (255, 255, 255) if hover else (238, 240, 250)
            pygame.draw.rect(self.base, bg, r, border_radius=10)
            pygame.draw.rect(self.base, (90, 110, 160), r, 2, border_radius=10)
            f = self.fonts.get(self.ui["choice_size"])
            label = opts[i] if i < len(opts) else "?"
            t = f.render(label, True, (35, 40, 60))
            self.base.blit(t, (r.centerx - t.get_width() // 2,
                               r.centery - t.get_height() // 2))

    def draw_question(self):
        blk = self.session.block
        u = self.ui
        box = pygame.Rect(int(self.W * u["ask_x"]), int(self.H * u["ask_y"]),
                          int(self.W * u["ask_w"]), int(self.H * u["ask_h"]))
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill((255, 255, 255, 240))
        self.base.blit(panel, box)
        pygame.draw.rect(self.base, (150, 152, 175), box, u["box_border"],
                         border_radius=u["box_radius"])
        f = self.fonts.get(u["ask_size"])
        p = f.render(blk.get("prompt", ""), True, (60, 60, 80))
        self.base.blit(p, (box.x + 18, box.y + 14))
        field = pygame.Rect(box.x + 18, box.y + 52, box.width - 36, 44)
        pygame.draw.rect(self.base, (246, 246, 250), field, border_radius=8)
        pygame.draw.rect(self.base, (120, 130, 170), field, 2, border_radius=8)
        caret = "_" if (pygame.time.get_ticks() // 500) % 2 == 0 else ""
        t = f.render(self.input_text + caret, True, (30, 30, 45))
        self.base.blit(t, (field.x + 10, field.centery - t.get_height() // 2))
        hint = self.fonts.get(15).render("输入后按回车确认", True, (140, 140, 160))
        self.base.blit(hint, (box.x + 18, box.bottom - 26))

    def draw_menu(self):
        self.buttons = []
        dim = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 150))
        self.base.blit(dim, (0, 0))
        panel = pygame.Rect(self.W // 2 - 190, self.H // 2 - 310, 380, 640)
        pygame.draw.rect(self.base, (250, 250, 254), panel, border_radius=14)
        f = self.fonts.get(24, bold=True)
        t = f.render("菜单", True, (40, 40, 60))
        self.base.blit(t, (panel.centerx - t.get_width() // 2, panel.y + 22))

        if getattr(self, "about_only", False):
            f2 = self.fonts.get(17)
            about = (self.session.options or {}).get("about") or "作者还没写关于内容。"
            y = panel.y + 80
            for line in _wrap_plain(about, 24):
                s = f2.render(line, True, (70, 70, 90))
                self.base.blit(s, (panel.x + 28, y))
                y += 26
            self.buttons.append(render.Button(
                pygame.Rect(panel.centerx - 70, panel.bottom - 66, 140, 44),
                "返回", self._back))
        else:
            items = [("保存进度", lambda: self.open_saveload(True)),
                     ("读取进度", lambda: self.open_saveload(False)),
                     ("历史记录", self.open_backlog),
                     ("文字速度 " + ("瞬间" if self.settings.text_speed < 0
                                  else "%d 字/秒" % int(self.settings.text_speed)),
                      self.cycle_speed),
                     ("文字大小 %d%%" % int(self.settings.font_scale * 100),
                      self.cycle_font_scale),
                     ("行距 %.1f" % self.settings.line_spacing,
                      self.cycle_line_spacing),
                     ("对话框透明度 %s" % ("默认" if self.settings.box_alpha is None
                                       else "%d%%" % int(self.settings.box_alpha / 255.0 * 100)),
                      self.cycle_box_alpha),
                     ("打字机 %s" % ("开" if self.settings.typewriter else "关"),
                      self.toggle_typewriter),
                     ("字体：%s" % (self.settings.font_name or "剧本默认"),
                      self.cycle_font),
                     ("BGM 音量 %d%%" % int(self.settings.vol["bgm"] * 100),
                      lambda: self.cycle_vol("bgm")),
                     ("音效音量 %d%%" % int(self.settings.vol["se"] * 100),
                      lambda: self.cycle_vol("se")),
                     ("语音音量 %d%%" % int(self.settings.vol["voice"] * 100),
                      lambda: self.cycle_vol("voice")),
                     ("重听语音", self.replay_voice),
                     ("全屏：%s  (F11)" % ("开" if self.settings.fullscreen else "关"),
                      self.toggle_fullscreen),
                     ("返回游戏", self._back),
                     ("回到标题", self._to_title)]
            y = panel.y + 70
            for label, act in items:
                self.buttons.append(render.Button(
                    pygame.Rect(panel.x + 40, y, panel.width - 80, 32), label, act))
                y += 34
        self.draw_buttons(18)

    def _back(self):
        self.about_only = False
        self.state = self.overlay_from
        self.buttons = []

    def _to_title(self):
        self.about_only = False
        self.state = TITLE
        self.buttons = []

    def cycle_speed(self):
        v = self.settings.text_speed
        self.settings.text_speed = -1 if v > 200 else (v * 2 if v > 0 else 45)

    def cycle_vol(self, kind):
        v = self.settings.vol[kind] + 0.2
        if v > 1.01:
            v = 0.0
        self.settings.vol[kind] = v
        self.audio.set_volume(kind, v)

    # ------------------------------------------------------------------ #
    # 第 2 期 #8：设置面板的循环调节项
    # ------------------------------------------------------------------ #
    def cycle_font_scale(self):
        # 0.8 -> 1.0 -> 1.2 -> 1.4 -> 1.6 -> 回到 0.8
        steps = [0.8, 1.0, 1.2, 1.4, 1.6]
        i = steps.index(round(self.settings.font_scale, 2)) \
            if round(self.settings.font_scale, 2) in steps else 0
        self.settings.font_scale = steps[(i + 1) % len(steps)]

    def cycle_line_spacing(self):
        # 1.2 -> 1.4 -> 1.6 -> 1.8 -> 2.0 -> 回到 1.2
        steps = [1.2, 1.4, 1.6, 1.8, 2.0]
        i = steps.index(round(self.settings.line_spacing, 2)) \
            if round(self.settings.line_spacing, 2) in steps else 0
        self.settings.line_spacing = steps[(i + 1) % len(steps)]

    def cycle_box_alpha(self):
        # None(默认) -> 不透明 -> 渐透 -> 更透 -> 最透 -> 回到默认
        seq = [None, 255, 200, 150, 100]
        try:
            i = seq.index(self.settings.box_alpha)
        except (ValueError, TypeError):
            i = 0
        self.settings.box_alpha = seq[(i + 1) % len(seq)]

    def toggle_typewriter(self):
        self.settings.typewriter = not self.settings.typewriter

    def cycle_font(self):
        choices = FONT_CHOICES
        try:
            i = choices.index(self.settings.font_name)
        except ValueError:
            i = 0
        self.settings.font_name = choices[(i + 1) % len(choices)]
        self._apply_font()

    def _apply_font(self):
        """按当前 font_name 重建字体集；"" 时用剧本头部的 Font=。"""
        name = self.settings.font_name
        self.fonts = render.FontSet(
            render.find_font_file(name if name else self.script.font))

    def replay_voice(self):
        """重听最后一句语音（第 2 期 #10，T5 提供 replay_voice；未实现就提示，不崩）。"""
        rp = getattr(self.audio, "replay_voice", None)
        if not callable(rp):
            if self.dev_mode:
                self.pending_toasts.append("语音重听功能尚未就绪")
            return
        try:
            if not rp():
                if self.dev_mode:
                    self.pending_toasts.append("没有可重听的语音")
        except Exception:                              # noqa: BLE001
            pass

    def draw_backlog(self):
        self.buttons = []
        dim = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 180))
        self.base.blit(dim, (0, 0))
        panel = pygame.Rect(int(self.W * 0.08), int(self.H * 0.08),
                            int(self.W * 0.84), int(self.H * 0.84))
        pygame.draw.rect(self.base, (250, 250, 254), panel, border_radius=14)
        f = self.fonts.get(20)
        fb = self.fonts.get(20, bold=True)
        hist = self.session.runtime.history
        start = self.backlog_scroll
        y = panel.y + 24
        for who, text in hist[start:start + 14]:
            if who:
                t = fb.render(who + "：", True, (90, 110, 160))
                self.base.blit(t, (panel.x + 26, y))
                x = panel.x + 26 + t.get_width()
            else:
                x = panel.x + 26
            s = f.render(text[:34], True, (60, 60, 78))
            self.base.blit(s, (x, y))
            y += 30
        hint = self.fonts.get(15).render("滚轮翻页 · Esc 返回", True, (150, 150, 170))
        self.base.blit(hint, (panel.centerx - hint.get_width() // 2, panel.bottom - 30))

    def draw_saveload(self):
        self.buttons = []
        dim = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 170))
        self.base.blit(dim, (0, 0))
        panel = pygame.Rect(int(self.W * 0.1), int(self.H * 0.12),
                            int(self.W * 0.8), int(self.H * 0.76))
        pygame.draw.rect(self.base, (250, 250, 254), panel, border_radius=14)
        title = "保存进度" if self.save_mode else "读取进度"
        t = self.fonts.get(23, bold=True).render(title, True, (40, 40, 60))
        self.base.blit(t, (panel.centerx - t.get_width() // 2, panel.y + 18))

        # T2 是否提供缩略图读写；拿不到就走纯文字（向后兼容）
        thumb_fn = getattr(savemod, "thumb_path", None)
        has_fn = getattr(savemod, "has_thumb", None)
        thumb_ok = callable(thumb_fn) and callable(has_fn)

        slots = savemod.list_slots(self.root)
        w = (panel.width - 60) // 2
        for i in range(savemod.SLOTS):
            n = i + 1
            snap = slots[i]
            col, row = i % 2, i // 2
            r = pygame.Rect(panel.x + 24 + col * (w + 12),
                             panel.y + 70 + row * 62, w, 52)
            img = None
            # 有缩略图就画出来（约 120×54），否则回退到现在的文字描述
            if thumb_ok and has_fn(self.root, n):
                surf = self._load_thumb(thumb_fn(self.root, n), r)
                if surf is not None:
                    img = pygame.Surface(r.size, pygame.SRCALPHA)
                    img.blit(surf, (8, (r.height - surf.get_height()) // 2))
                    f = self.fonts.get(15)
                    label = f.render("%d. %s" % (n, savemod.describe(snap)),
                                     True, (40, 40, 60))
                    img.blit(label, (140, r.height // 2 - 9))
            if self.save_mode:
                act = (lambda nn=n: self.do_save(nn))
            else:
                act = (lambda nn=n: self.do_load(nn))
            self.buttons.append(render.Button(
                r, "%d. %s" % (n, savemod.describe(snap)), act, img))

        # 第 2 期 #6：导入 / 导出存档（用系统文件对话框，结果以提示反馈）
        bw = (w - 12) // 2
        self.buttons.append(render.Button(
            pygame.Rect(panel.x + 24, panel.bottom - 108, bw, 36),
            "导出存档…", self.export_save))
        self.buttons.append(render.Button(
            pygame.Rect(panel.x + 24 + bw + 12, panel.bottom - 108, bw, 36),
            "导入存档…", self.import_save))
        self.buttons.append(render.Button(
            pygame.Rect(panel.centerx - 70, panel.bottom - 60, 140, 42),
            "返回", self._back))
        self.draw_buttons(17)

    def _load_thumb(self, path, r):
        """读存档缩略图并缩放成按钮里能放下的小图（约 120×54）。"""
        try:
            surf = pygame.image.load(path)
        except Exception:                              # noqa: BLE001
            return None
        return render.fit_into(surf, 120, 54)

    def do_save(self, n):
        savemod.write_slot(self.root, n, self.session.snapshot())
        self.settings.quick_slot = n
        self.pending_toasts.append("已保存到第 %d 格" % n)
        # 缩略图：把当前画面存成小图（T2 提供 thumb_path；未提供就跳过）
        thumb_fn = getattr(savemod, "thumb_path", None)
        if callable(thumb_fn):
            try:
                pygame.image.save(self.screen, thumb_fn(self.root, n))
            except Exception as e:                         # noqa: BLE001
                # 缩略图写失败（没权限等）不能影响存档本身
                if self.dev_mode:
                    self.pending_toasts.append("缩略图保存失败：%s" % e)

    def quick_save(self):
        """F5：快速存到上次用的槽（没有就槽 1）。"""
        self.do_save(self.settings.quick_slot)

    def quick_load(self):
        """F9：快速读上次用的槽。"""
        self.do_load(self.settings.quick_slot)

    def do_load(self, n):
        snap = savemod.read_slot(self.root, n)
        if not snap:
            self.pending_toasts.append("第 %d 格是空的" % n)
            return
        self._prev_scene = None       # 读档不补间，直接落到终态
        self.anim.clear()
        try:
            self.session.restore(snap)
            self.apply_effects()
            self.reveal = 0.0
            self._shown_chars = 0
            # 读档点之前的台词都算「看过」，快进时可以直接跳过
            self.seen.update((w, t) for w, t in self.session.runtime.history)
            self.sync_state()
            self.state = self.overlay_from if self.overlay_from != SAVELOAD else ADVANCE
        except Exception as e:                       # noqa: BLE001
            self.error_text = "读档失败：%s\n%s" % (e, format_exception(e))
            self.state = ERROR

    # ------------------------------------------------------------------ #
    # 第 2 期 #6：存档导入 / 导出（用系统文件对话框，结果以提示反馈）
    # ------------------------------------------------------------------ #
    def export_save(self):
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            out = filedialog.asksaveasfilename(
                title="导出存档",
                defaultextension=".stmgsav",
                filetypes=[("STMG 存档包", "*.stmgsav")])
            root.destroy()
        except Exception as e:                         # noqa: BLE001
            if self.dev_mode:
                self.pending_toasts.append("打开文件对话框失败：%s" % e)
            return
        if not out:
            return
        fn = getattr(savemod, "export_slots", None)
        if not callable(fn):
            self.pending_toasts.append("存档导入导出功能尚未就绪")
            return
        try:
            res = fn(self.root, self.script.title, out)
            ok = bool(res[0])
            msg = res[1] if len(res) > 1 else ("导出成功" if ok else "导出失败")
        except Exception as e:                         # noqa: BLE001
            ok, msg = False, "导出失败：%s" % e
        self.pending_toasts.append(msg)

    def import_save(self):
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            src = filedialog.askopenfilename(
                title="导入存档",
                filetypes=[("STMG 存档包", "*.stmgsav")])
            root.destroy()
        except Exception as e:                         # noqa: BLE001
            if self.dev_mode:
                self.pending_toasts.append("打开文件对话框失败：%s" % e)
            return
        if not src:
            return
        fn = getattr(savemod, "import_slots", None)
        if not callable(fn):
            self.pending_toasts.append("存档导入导出功能尚未就绪")
            return
        try:
            res = fn(src, self.root)
            ok = bool(res[0])
            msg = res[1] if len(res) > 1 else ("导入成功" if ok else "导入失败")
        except Exception as e:                         # noqa: BLE001
            ok, msg = False, "导入失败：%s" % e
        self.pending_toasts.append(msg)

    # ------------------------------------------------------------------ #
    def _error_rows(self):
        """解析错误界面要逐行显示的内容，供 draw_error 与测试复用。"""
        max_chars = max(8, (self.W - 80) // 17)

        def clip(text):
            return text if len(text) <= max_chars else text[:max_chars - 1] + "…"

        rows = []
        for i in self.script_errors:
            tag = "错误" if i.level == "error" else "提示"
            pos = "行 %d" % i.line if i.line else "全局"
            head = "[%s] %s  %s" % (tag, pos, i.message)
            color = (255, 200, 200) if i.level == "error" else (210, 214, 180)
            rows.append((clip(head), color))
            if self.dev_mode and i.hint:
                rows.append((clip("    -> " + i.hint), (175, 188, 214)))
            if i.level == "error":
                rows.append(("", color))
        return rows

    def draw_error(self):
        self.base.fill((20, 18, 26))
        f_title = self.fonts.get(28, bold=True)
        t = f_title.render("An error has occurred.", True, (255, 110, 110))
        self.base.blit(t, (40, 30))

        if self.error_mode == "script" and self.script_errors:
            self.buttons = []
            errs = [i for i in self.script_errors if i.level == "error"]
            warns = [i for i in self.script_errors if i.level == "warn"]
            f_sub = self.fonts.get(20)
            if self.dev_mode:
                sub = "剧本解析发现 %d 个错误" % len(errs)
                if warns:
                    sub += "、%d 条提示" % len(warns)
                sub += "，无法启动。下面是详细列表："
            else:
                sub = "游戏剧本存在 %d 处错误，无法启动，请联系作者修复。" % len(errs)
            s = f_sub.render(sub, True, (235, 225, 225))
            self.base.blit(s, (40, 78))

            f2 = self.fonts.get(17)
            line_h = 24
            view_top = 120
            view_bottom = self.H - 96

            rows = self._error_rows()
            total = len(rows) * line_h
            max_scroll = max(0, total - (view_bottom - view_top))
            self.error_scroll = min(self.error_scroll, max_scroll)
            y = view_top - self.error_scroll
            for text, color in rows:
                if y + line_h < view_top:
                    y += line_h
                    continue
                if y > view_bottom:
                    break
                if text:
                    surf = f2.render(text, True, color)
                    self.base.blit(surf, (40, y))
                y += line_h

            r = pygame.Rect(self.W - 150, self.H - 64, 110, 40)
            self.buttons.append(render.Button(
                r, "退出", lambda: setattr(self, "running", False)))
            self.draw_buttons(18)
            hint = self.fonts.get(15).render(
                "回车 / Esc 退出  ·  滚轮翻看", True, (180, 160, 160))
            self.base.blit(hint, (40, self.H - 40))
            return

        # ---- 运行时致命错误（原有逻辑）----
        if not self.dev_mode:
            msg = self.fonts.get(20).render(
                "游戏遇到了问题，细节已写进日志。按回车继续。", True, (230, 220, 220))
            self.base.blit(msg, (40, 90))
        else:
            f2 = self.fonts.get(17)
            y = 86
            for line in self.error_text.splitlines()[:24]:
                s = f2.render(line[:96], True, (235, 225, 225))
                self.base.blit(s, (40, y))
                y += 24
        hint = self.fonts.get(16).render("按回车继续", True, (200, 170, 170))
        self.base.blit(hint, (40, self.H - 40))

    def draw_achievements(self):
        """成就解锁的小卡片，居中偏上、金色描边，几秒后淡出。"""
        u = self.ui
        cx = int(self.W * 0.5)
        y = int(self.H * 0.16)
        title_f = self.fonts.get(19, bold=True)
        name_f = self.fonts.get(23, bold=True)
        for card in self.achieve_popups:
            name = card.get("name", "")
            tw = max(title_f.size("★ 成就解锁")[0], name_f.size(name)[0]) + 44
            th = 86
            alpha = min(1.0, max(0.0, card["ttl"] / 0.5))
            surf = pygame.Surface((tw, th), pygame.SRCALPHA)
            surf.set_alpha(int(255 * alpha))
            pygame.draw.rect(surf, (38, 34, 26, 235),
                             pygame.Rect(0, 0, tw, th), border_radius=12)
            pygame.draw.rect(surf, (232, 192, 96, 255),
                             pygame.Rect(6, 6, tw - 12, 4), border_radius=2)
            t1 = title_f.render("★ 成就解锁", True, (240, 206, 112))
            t2 = name_f.render(name, True, (255, 248, 236))
            surf.blit(t1, (tw // 2 - t1.get_width() // 2, 18))
            surf.blit(t2, (tw // 2 - t2.get_width() // 2, 46))
            self.base.blit(surf, (cx - tw // 2, y))
            y += th + 12

    def draw_ending(self):
        self.base.fill((18, 20, 30))
        text = "感谢游玩"
        f = self.fonts.get(int(self.H * 0.06), bold=True)
        t = f.render(text, True, (255, 255, 255))
        self.base.blit(t, ((self.W - t.get_width()) // 2, int(self.H * 0.40)))
        f2 = self.fonts.get(18)
        s = f2.render("点击或按回车结束", True, (170, 175, 195))
        self.base.blit(s, ((self.W - s.get_width()) // 2, int(self.H * 0.56)))
        if pygame.mouse.get_pressed()[0]:
            self.running = False


def _wrap_plain(text, per_line):
    out, line = [], ""
    for ch in text:
        line += ch
        if len(line) >= per_line or ch == "\n":
            out.append(line.strip())
            line = ""
    if line.strip():
        out.append(line.strip())
    return out
