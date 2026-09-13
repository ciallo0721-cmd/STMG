# -*- coding: utf-8 -*-
"""STMG 界面配置 —— 让**项目自己**决定界面长什么样。

引擎默认外观写在下面的 DEFAULTS 里。项目目录下放一个 `custom/gui.py`，
里面写：

    CONFIG = {
        "box_h": 0.26,
        "title_bg": "bg/title.png",
        "title_bgm": "music/title.mp3",
    }

引擎启动时会把它合并进来（只覆盖写了的项，没写的用默认值）。
`custom/markdown.py` 则是用来替换内联标记渲染规则的。

这个文件被引擎和转换器共用，改默认值请直接改 DEFAULTS。
"""

import os

# --------------------------------------------------------------------------- #
# 默认外观
# --------------------------------------------------------------------------- #
DEFAULTS = {
    # ---------- 对话框 ----------
    "box_x": 0.05,               # 左边距（占屏宽 0~1）
    "box_y": 0.03,               # 距屏幕底部
    "box_w": 0.90,               # 宽
    "box_h": 0.30,               # 高
    "box_radius": 10,            # 圆角
    "box_color": (252, 252, 255),
    "box_alpha": 232,            # 0~255，越小越透
    "box_border": 2,             # 边框粗细，0 = 不画
    "box_border_color": (150, 152, 175),
    "text_pad": 26,              # 台词距框内边
    "text_size": 23,             # 正文字号
    "text_color": None,          # None = 用 md 标记里的颜色，黑色默认

    # ---------- 名字框 ----------
    "name_size": 22,
    "name_bg": (72, 96, 140),
    "name_color": (255, 255, 255),
    "name_h": 0.075,

    # ---------- 立绘 ----------
    "sprite_x": {"left": 0.24, "center": 0.5, "right": 0.76,
                 "farleft": 0.13, "farright": 0.87},
    "sprite_w": 0.42,            # 立绘最大宽（占屏宽）
    "sprite_h": 0.76,            # 立绘最大高（占屏高）
    "sprite_bottom": 0.78,       # 脚底位置（占屏高）
    "sprite_scale_default": 1.0,  # 立绘默认尺寸倍数（1.0 = 不改）
    "sprite_idle": False,         # 是否开启空闲微动（默认关，老行为不变）
    "sprite_idle_amp": 5,         # 微动竖直浮动幅度（像素）
    "sprite_idle_rotate": 0,      # 微动附加旋转幅度（度）

    # ---------- S.picture 叠加图 ----------
    "pic_w": 0.6,
    "pic_h": 0.6,
    "pic_center_y": 0.5,         # 图片底边落在屏幕的哪个高度

    # ---------- 标题界面 ----------
    "title_bg": "",              # 标题背景图（相对项目目录，空 = 用渐变）
    "title_pic": "",             # 标题图，空 = 自动找 gui/button/title.png
    "title_bgm": "",             # 标题 BGM（进游戏时会自动停）
    "title_bgm_volume": 0.7,
    "title_y": 0.18,             # 标题纵向位置
    "title_size": 0.075,         # 标题字号（占屏高）
    "title_top": (30, 32, 56),   # 渐变背景上边色
    "title_bottom": (70, 62, 106),

    # ---------- 选择支 ----------
    "choice_w": 0.52,
    "choice_h": 54,
    "choice_gap": 16,
    "choice_size": 22,
    "choice_radius": 10,

    # ---------- 询问输入 ----------
    "ask_x": 0.20,
    "ask_y": 0.52,
    "ask_w": 0.60,
    "ask_h": 0.20,
    "ask_size": 20,

    # ---------- 右上角提示 ----------
    "toast_size": 16,
}


def _clone(v):
    return dict(v) if isinstance(v, dict) else v


def load(root):
    """读 <root>/custom/gui.py 的 CONFIG，和默认值合并后返回。

    读不了也不影响游戏，错误塞在返回值里的 `_error` 里面。
    """
    cfg = {k: _clone(v) for k, v in DEFAULTS.items()}
    path = os.path.join(root, "custom", "gui.py")
    if not os.path.isfile(path):
        return cfg
    try:
        ns = {"__file__": path, "__name__": "stmg_custom_gui"}
        with open(path, "r", encoding="utf-8-sig") as f:
            exec(compile(f.read(), path, "exec"), ns)      # noqa: S102 - 玩家自己的项目文件
    except Exception as e:                                 # noqa: BLE001
        cfg["_error"] = "custom/gui.py 加载失败：%s: %s" % (type(e).__name__, e)
        return cfg

    user = ns.get("CONFIG") or {}
    if not isinstance(user, dict):
        cfg["_error"] = "custom/gui.py 里的 CONFIG 不是字典"
        return cfg
    for k, v in user.items():
        if v is None:
            continue
        if k not in cfg:
            cfg.setdefault("_unknown", []).append(k)
            continue
        if isinstance(cfg[k], dict) and isinstance(v, dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


def load_markdown(root):
    """把 <root>/custom/markdown.py 的 render() 接到 stmg.markdown 上。

    返回 None 表示没问题，返回字符串表示失败原因。
    """
    path = os.path.join(root, "custom", "markdown.py")
    if not os.path.isfile(path):
        return None
    try:
        ns = {"__file__": path, "__name__": "stmg_custom_markdown"}
        with open(path, "r", encoding="utf-8-sig") as f:
            exec(compile(f.read(), path, "exec"), ns)      # noqa: S102
    except Exception as e:                                 # noqa: BLE001
        return "custom/markdown.py 加载失败：%s: %s" % (type(e).__name__, e)

    fn = ns.get("render")
    if not callable(fn):
        return "custom/markdown.py 里没有 render(text) 函数"

    from . import markdown as mdmod
    mdmod.render = fn
    plain = ns.get("plain")
    if callable(plain):
        mdmod.plain = plain
    return None


def setup(root):
    """一次性搞定：返回 (配置, 错误信息或 None)。"""
    cfg = load(root)
    err = load_markdown(root) or cfg.get("_error")
    return cfg, err
