# -*- coding: utf-8 -*-
"""pygame 绘制层：Markdown run 排版、文本框、立绘占位、toast。

只负责「怎么画」，不负责「画什么」——场景状态在 session 里。
"""

import os

import pygame

from . import pack
from . import markdown as mdmod

# 中文字体候选，按顺序找第一个系统里有的
FONT_CANDIDATES = [
    "microsoftyaheiui", "microsoftyahei", "simhei", "simsun",
    "notosanscjksc", "sourcehansanssc", "arialunicodems", "dejavusans",
]

CODE_BG = (235, 235, 240)


# 找不到的时候直接去字体目录抓，按优先级排
FONT_FILES = ["msyh.ttc", "msyhbd.ttc", "msyh.ttf", "simhei.ttf", "simsun.ttc",
              "deng.ttf", "msjh.ttc", "notosanscjksc-regular.otf",
              "sourcehansanssc-regular.otf", "arialuni.ttf"]


def _font_dirs():
    win = os.environ.get("WINDIR", r"C:\Windows")
    return [os.path.join(win, "Fonts"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""),
                         "Microsoft", "Windows", "Fonts"),
            os.path.expanduser("~/.fonts"),
            "/usr/share/fonts", "/System/Library/Fonts"]


def find_font_file(preferred=None):
    """找一个能显示中文的字体文件。

    pygame.font.match_font 在某些 Windows 上会因为注册表里混进奇怪的值而抛
    TypeError，所以整段包了 try，失败了就直接翻字体目录。
    """
    names = []
    if preferred:
        names.append(preferred.lower().replace(" ", ""))
    names.extend(FONT_CANDIDATES)
    try:
        for n in names:
            p = pygame.font.match_font(n)
            if p and os.path.isfile(p):
                return p
    except Exception:                                # noqa: BLE001 - pygame 的老毛病
        pass

    wanted = [w.lower() for w in FONT_FILES]
    for d in _font_dirs():
        if not os.path.isdir(d):
            continue
        found = {}
        for dirpath, _dirs, files in os.walk(d):
            for fn in files:
                low = fn.lower()
                if low in wanted and low not in found:
                    found[low] = os.path.join(dirpath, fn)
            if len(found) >= 3:
                break
        for w in wanted:
            if w in found:
                return found[w]
    return None


class FontSet(object):
    """按 (字号, 粗体, 斜体) 缓存字体对象。"""

    def __init__(self, font_file=None, scale=1.0):
        self.file = font_file or find_font_file()
        self.scale = scale
        self._cache = {}

    def get(self, size, bold=False, italic=False):
        size = max(10, int(round(size * self.scale)))
        key = (size, bold, italic)
        if key not in self._cache:
            f = pygame.font.Font(self.file, size)
            f.set_bold(bold)
            f.set_italic(italic)
            self._cache[key] = f
        return self._cache[key]


# --------------------------------------------------------------------------- #
# 排版
# --------------------------------------------------------------------------- #
BREAK_BEFORE = "。！？、，．：；）」』】”…!?,.:;)]}"


def _units(text):
    """把文本切成排版单位：中文按字切，英文按词切。"""
    out, buf = [], ""
    for ch in text:
        if ch == "\n":
            if buf:
                out.append(buf)
                buf = ""
            out.append("\n")
        elif ord(ch) < 128 and (ch.isalnum() or ch in "-_'"):
            buf += ch
        else:
            if buf:
                out.append(buf)
                buf = ""
            out.append(ch)
    if buf:
        out.append(buf)
    return out


def layout(runs, fonts, max_width, base_size=22, line_spacing=1.45):
    """把 run 列表排成行。

    返回 [[(文本, 样式, 宽度), ...], ...]
    """
    lines, cur, cur_w = [], [], 0.0
    line_h = base_size * line_spacing
    for run in runs:
        size = run.get("size") or base_size
        font = fonts.get(size, run.get("bold"), run.get("italic"))
        style = dict(run)
        for unit in _units(run["t"]):
            if unit == "\n":
                lines.append(cur)
                cur, cur_w = [], 0.0
                continue
            w = font.size(unit)[0]
            if cur and cur_w + w > max_width:
                # 行首不该出现的标点，先挤在上一行
                if unit in BREAK_BEFORE and cur:
                    cur[-1] = (cur[-1][0] + unit, cur[-1][1], cur[-1][2] + w)
                    lines.append(cur)
                    cur, cur_w = [], 0.0
                    continue
                lines.append(cur)
                cur, cur_w = [], 0.0
            if cur and cur[-1][1] is style:
                cur[-1] = (cur[-1][0] + unit, style, cur[-1][2] + w)
            else:
                cur.append((unit, style, w))
            cur_w += w
    if cur:
        lines.append(cur)
    return lines, line_h


def total_chars(lines):
    return sum(len(frag[0]) for line in lines for frag in line)


def reveal(lines, budget):
    """只显示前 budget 个字符，返回新行列表。"""
    if budget is None:
        return lines
    out, left = [], max(0, budget)
    for line in lines:
        new_line = []
        for text, style, _w in line:
            if left <= 0:
                break
            take = text[:left]
            left -= len(take)
            if take:
                new_line.append((take, style, _w))
        out.append(new_line)
        if left <= 0:
            break
    return out


def draw_lines(surface, lines, fonts, x, y, line_h, base_size=22,
               default_color=(40, 40, 48), shadow=None):
    for line in lines:
        cx = x
        for text, style, _w in line:
            size = style.get("size") or base_size
            font = fonts.get(size, style.get("bold"), style.get("italic"))
            color = style.get("color") or default_color
            if len(color) == 7 and color.startswith("#"):
                rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
            elif isinstance(color, (list, tuple)):
                rgb = tuple(color)
            else:
                rgb = default_color
            surf = font.render(text, True, rgb)
            cx_use = cx
            if style.get("code"):
                bg = pygame.Surface((surf.get_width() + 4, surf.get_height() + 2),
                                    pygame.SRCALPHA)
                bg.fill(CODE_BG + (220,))
                surface.blit(bg, (cx_use - 2, y - 1))
            if shadow:
                sh = font.render(text, True, shadow)
                surface.blit(sh, (cx_use + 1, y + 1))
            surface.blit(surf, (cx_use, y))
            if style.get("strike"):
                mid = y + surf.get_height() // 2
                pygame.draw.line(surface, rgb, (cx_use, mid),
                                 (cx_use + surf.get_width(), mid), 2)
            cx += surf.get_width()
        y += line_h
    return y


# --------------------------------------------------------------------------- #
# 图片
# --------------------------------------------------------------------------- #
_image_cache = {}


def load_image(path, size=None):
    key = (path, size)
    if key in _image_cache:
        return _image_cache[key]
    img = None
    try:
        if path and pack.exists(path):
            raw = pygame.image.load(pack.open_binary(path))
            try:
                raw = raw.convert_alpha()
            except pygame.error:
                raw = raw.convert()
            img = pygame.transform.smoothscale(raw, size) if size else raw
    except (pygame.error, OSError, KeyError):
        img = None
    _image_cache[key] = img
    return img


def fit_into(img, w, h):
    """等比缩放到刚好放进 w x h。"""
    iw, ih = img.get_size()
    if iw == 0 or ih == 0:
        return img
    k = min(w / float(iw), h / float(ih))
    if abs(k - 1.0) < 0.01:
        return img
    return pygame.transform.smoothscale(img, (max(1, int(iw * k)),
                                              max(1, int(ih * k))))


def draw_placeholder(surface, rect, label, hue=0):
    """素材缺失时画个好看点的占位块，免得黑屏让人以为引擎坏了。"""
    base = [(58, 62, 84), (74, 60, 88), (52, 74, 78), (86, 70, 56)][hue % 4]
    pygame.draw.rect(surface, base, rect)
    for i in range(rect.height):
        k = i / float(max(1, rect.height))
        c = (int(base[0] * (1 - k * 0.5)), int(base[1] * (1 - k * 0.5)),
             int(base[2] * (1 - k * 0.5)))
        pygame.draw.line(surface, c, (rect.x, rect.y + i),
                         (rect.right, rect.y + i))
    pygame.draw.rect(surface, (255, 255, 255), rect, 2)
    try:
        # 用 pygame 自带的默认字体，别走 SysFont —— 它在部分 Windows 上会炸
        font = pygame.font.Font(None, 22)
        txt = font.render("[missing] " + os.path.basename(label or "?"),
                          True, (255, 255, 255))
        surface.blit(txt, (rect.centerx - txt.get_width() // 2,
                           rect.centery - txt.get_height() // 2))
    except pygame.error:
        pass


# --------------------------------------------------------------------------- #
# 控件
# --------------------------------------------------------------------------- #
class Button(object):
    def __init__(self, rect, label, action, image=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.action = action
        self.image = image
        self.hover = False

    def draw(self, surface, fonts, size=20, mouse=None):
        # 按钮每帧都会重新建，hover 不能指望 MOUSEMOTION 事件留在对象上，
        # 直接拿当前鼠标位置算，否则「鼠标移上去没反应」。
        if mouse is not None:
            self.hover = self.rect.collidepoint(mouse)
        if self.image:
            surface.blit(self.image, self.rect)
            if self.hover:
                hl = pygame.Surface(self.rect.size, pygame.SRCALPHA)
                hl.fill((255, 255, 255, 46))
                surface.blit(hl, self.rect)
            return
        bg = (250, 250, 253) if self.hover else (232, 232, 242)
        pygame.draw.rect(surface, bg, self.rect, border_radius=8)
        pygame.draw.rect(surface, (150, 150, 175), self.rect, 2, border_radius=8)
        f = fonts.get(size)
        t = f.render(self.label, True, (45, 45, 60))
        surface.blit(t, (self.rect.centerx - t.get_width() // 2,
                         self.rect.centery - t.get_height() // 2))

    def handle(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return self.action
        return None


def draw_toasts(surface, fonts, toasts, w, start_y=12, size=16):
    """右上角的 STM.display / STM.python 提示。"""
    y = start_y
    for text in toasts[-5:]:
        f = fonts.get(size)
        t = f.render(text[:48], True, (255, 255, 255))
        pad = 8
        box = pygame.Surface((t.get_width() + pad * 2, t.get_height() + pad),
                             pygame.SRCALPHA)
        box.fill((30, 34, 48, 205))
        surface.blit(box, (w - box.get_width() - 12, y))
        surface.blit(t, (w - box.get_width() - 12 + pad, y + pad // 2))
        y += box.get_height() + 6


def draw_transition(surface, kind, progress, w, h, color=(16, 16, 22), prev=None):
    """转场遮罩：surface 已经画好「新的一帧」，prev 是「上一帧」的快照。

    三种效果（kind）：
        fade      淡入淡出：遮罩透明度 0->255->0，画面在中点（全遮罩的瞬间）换景
        dissolve  交叉溶解：上一帧直接叠在新帧上，透明度 1->0 渐隐
        flash     白闪：一层白光在中点最亮，用来掩盖瞬间的换景
    prev 为 None 时退化为纯遮罩动画，不跨帧融合。
    """
    p = max(0.0, min(1.0, progress))

    if kind == "dissolve":
        if prev is not None:
            layer = prev.copy()
            layer.set_alpha(int(255 * (1.0 - p)))
            surface.blit(layer, (0, 0))
        return

    if kind == "flash":
        a = int(255 * (1.0 - abs(2.0 * p - 1.0)))
        if a > 0:
            mask = pygame.Surface((w, h), pygame.SRCALPHA)
            mask.fill((255, 255, 255, a))
            surface.blit(mask, (0, 0))
        return

    # fade（默认）：0->255->0，中点换景
    if p < 0.5 and prev is not None:
        surface.blit(prev, (0, 0))
    a = int(255 * (1.0 - abs(2.0 * p - 1.0)))
    if a > 0:
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        mask.fill((color[0], color[1], color[2], a))
        surface.blit(mask, (0, 0))


def md(text):
    # 走模块属性而不是直接引用函数，这样项目的 custom/markdown.py
    # 覆盖过 markdown.render 之后能立刻生效。
    return mdmod.render(text)
