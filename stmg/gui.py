# -*- coding: utf-8 -*-
"""STMG 主界面（pygame）。

界面状态：标题 / 对白 / 选择支 / 询问输入 / 菜单 / 历史 / 存读档 / 报错 / 结束
渲染统一画在一张 base 画布上，再整体缩放到窗口，所以剧本写多大分辨率都能跑。
"""

import json
import os

import pygame

from . import render, save as savemod, uiconf
from .audio import Audio
from .errors import format_exception
from .session import Session

TITLE, ADVANCE, CHOOSE, QUESTION, MENU, BACKLOG, SAVELOAD, ERROR, ENDING = range(9)

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
            except (ValueError, OSError):
                pass

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"text_speed": self.text_speed,
                           "auto_delay": self.auto_delay,
                           "vol": self.vol,
                           "fullscreen": self.fullscreen}, f, indent=1)
        except OSError:
            pass


class App(object):
    def __init__(self, script, options=None, dev_mode=True, auto=False,
                 script_errors=None):
        pygame.init()
        self.script = script
        self.dev_mode = dev_mode
        self.root = os.path.dirname(os.path.abspath(script.path))
        self.W, self.H = script.size
        self.settings = Settings(self.root)
        # 项目自定义界面：custom/gui.py（外观）+ custom/markdown.py（内联标记）
        self.ui, self.ui_error = uiconf.setup(self.root)

        self._open_window()
        self.base = pygame.Surface((self.W, self.H)).convert()

        self.fonts = render.FontSet(render.find_font_file(script.font))
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
        self.input_text = ""
        self.backlog_scroll = 0
        self.overlay_from = TITLE
        self.pending_toasts = []
        self.running = True

        # 项目自定义界面出问题的话，开发模式下提示一句（不影响游戏）
        if self.ui_error and self.dev_mode:
            self.pending_toasts.append("界面配置：" + self.ui_error)

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
        if self.session.toasts:
            self.pending_toasts.extend(self.session.toasts)

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
        if self.state in (ADVANCE, CHOOSE, QUESTION):
            if self.settings.text_speed < 0:
                self.reveal = 1e9
            else:
                self.reveal += self.settings.text_speed * dt
            if self.state == ADVANCE and self.is_revealed():
                if self.skip:
                    self.advance()
                elif self.auto:
                    self.auto_timer += dt
                    if self.auto_timer >= self.settings.auto_delay:
                        self.auto_timer = 0
                        self.advance()

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
        self.reveal = 0.0
        self.auto_timer = 0.0
        self.session.next_block()
        self.apply_effects()
        self.sync_state()

    def choose(self, index):
        self.reveal = 0.0
        self.session.answer(self.session.block["options"][index])
        self.apply_effects()
        self.sync_state()

    def submit_answer(self, text):
        self.reveal = 0.0
        self.session.answer(text)
        self.apply_effects()
        self.sync_state()

    def sync_state(self):
        blk = self.session.block
        t = blk["t"]
        if t == "say":
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

            if self.state in (TITLE, MENU, SAVELOAD, BACKLOG, ENDING, ERROR):
                for b in self.buttons:
                    act = b.handle(event)
                    if act:
                        act()
                        break
                if event.type == pygame.MOUSEBUTTONDOWN and self.state == BACKLOG:
                    self.backlog_scroll += -3 if event.button == 4 else 3 if event.button == 5 else 0
                    self.backlog_scroll = max(0, min(self.backlog_scroll,
                                                     max(0, len(self.session.runtime.history) - 6)))
                if event.type == pygame.MOUSEWHEEL and self.state == ERROR \
                        and self.error_mode == "script":
                    self.error_scroll = max(0, self.error_scroll - event.y * 3)
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
            if self.state in (MENU, BACKLOG, SAVELOAD):
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
                self.open_saveload(True)
            elif k == pygame.K_F9:
                self.open_saveload(False)
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
        y = int(self.H * 0.46)
        labels = [("开始游戏", self.start_game, "start.png"),
                  ("读取存档", lambda: self.open_saveload(False), ""),
                  ("设置", self.open_menu, "setting.png"),
                  ("关于", self.show_about, "about.png")]
        for i, (label, act, img) in enumerate(labels):
            r = pygame.Rect(cx - 110, y + i * 62, 220, 48)
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
        self.session.reset()
        self.apply_effects()
        self.reveal = 0.0
        self.sync_state()

    def show_about(self):
        self.overlay_from = TITLE
        self.state = MENU
        self.about_only = True

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
        bg = render.load_image(self.session.scene.get("bg", ""))
        if bg:
            bg = render.fit_into(bg, self.W, self.H)
            self.base.blit(bg, ((self.W - bg.get_width()) // 2,
                                (self.H - bg.get_height()) // 2))
        else:
            render.draw_placeholder(self.base, pygame.Rect(0, 0, self.W, int(self.H * 0.72)),
                                    self.session.scene.get("bg") or "背景", 0)

        pic = self.session.scene.get("picture", "")
        if pic:
            img = render.load_image(pic)
            if img:
                img = render.fit_into(img, int(self.W * self.ui["pic_w"]),
                                      int(self.H * self.ui["pic_h"]))
                self.base.blit(img, ((self.W - img.get_width()) // 2,
                                     int(self.H * self.ui["pic_center_y"])
                                     - img.get_height()))
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
            path = item.get("path", "")
            cx = int(self.W * u["sprite_x"].get(item.get("pos", "center"), 0.5))
            bottom = int(self.H * u["sprite_bottom"])
            img = render.load_image(path)
            if img:
                img = render.fit_into(img, int(self.W * u["sprite_w"]),
                                      int(self.H * u["sprite_h"]))
                self.base.blit(img, (cx - img.get_width() // 2,
                                     bottom - img.get_height()))
            else:
                w, h = int(self.W * 0.2), int(self.H * 0.54)
                r = pygame.Rect(cx - w // 2, bottom - h, w, h)
                render.draw_placeholder(self.base, r, path, i + 1)

        self.draw_textbox()

    def draw_textbox(self):
        u = self.ui
        box = self.box_rect()
        img = render.load_image(self.asset("textbox", "box.png"), box.size)
        if img:
            self.base.blit(img, box)
        else:
            panel = pygame.Surface(box.size, pygame.SRCALPHA)
            c = u["box_color"]
            panel.fill((c[0], c[1], c[2], u["box_alpha"]))
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
        lines, line_h = render.layout(runs, self.fonts,
                                      box.width - pad * 2,
                                      base_size=u["text_size"])
        shown = render.reveal(lines, int(self.reveal))
        render.draw_lines(self.base, shown, self.fonts, box.x + pad, y,
                          line_h, base_size=u["text_size"])

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
        panel = pygame.Rect(self.W // 2 - 190, self.H // 2 - 224, 380, 448)
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
                     ("BGM 音量 %d%%" % int(self.settings.vol["bgm"] * 100),
                      lambda: self.cycle_vol("bgm")),
                     ("音效音量 %d%%" % int(self.settings.vol["se"] * 100),
                      lambda: self.cycle_vol("se")),
                     ("语音音量 %d%%" % int(self.settings.vol["voice"] * 100),
                      lambda: self.cycle_vol("voice")),
                     ("全屏：%s  (F11)" % ("开" if self.settings.fullscreen else "关"),
                      self.toggle_fullscreen),
                     ("返回游戏", self._back),
                     ("回到标题", self._to_title)]
            y = panel.y + 70
            for label, act in items:
                self.buttons.append(render.Button(
                    pygame.Rect(panel.x + 40, y, panel.width - 80, 32), label, act))
                y += 36
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

        slots = savemod.list_slots(self.root)
        w = (panel.width - 60) // 2
        for i in range(savemod.SLOTS):
            col, row = i % 2, i // 2
            r = pygame.Rect(panel.x + 24 + col * (w + 12), panel.y + 70 + row * 62, w, 52)
            if self.save_mode:
                act = (lambda n=i + 1: self.do_save(n))
            else:
                act = (lambda n=i + 1: self.do_load(n))
            self.buttons.append(render.Button(
                r, "%d. %s" % (i + 1, savemod.describe(slots[i])), act))
        self.buttons.append(render.Button(
            pygame.Rect(panel.centerx - 70, panel.bottom - 60, 140, 42),
            "返回", self._back))
        self.draw_buttons(17)

    def do_save(self, n):
        savemod.write_slot(self.root, n, self.session.snapshot())
        self.pending_toasts.append("已保存到第 %d 格" % n)

    def do_load(self, n):
        snap = savemod.read_slot(self.root, n)
        if not snap:
            self.pending_toasts.append("第 %d 格是空的" % n)
            return
        try:
            self.session.restore(snap)
            self.apply_effects()
            self.reveal = 0.0
            self.sync_state()
            self.state = self.overlay_from if self.overlay_from != SAVELOAD else ADVANCE
        except Exception as e:                       # noqa: BLE001
            self.error_text = "读档失败：%s\n%s" % (e, format_exception(e))
            self.state = ERROR

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
