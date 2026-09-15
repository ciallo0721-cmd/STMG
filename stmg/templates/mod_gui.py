# -*- coding: utf-8 -*-
"""桌面端外观参数。

这里是整个美化包里**唯一**允许的 Python 文件，而且只能做一件事：
声明一个 CONFIG 字典。写别的（import、函数、open、eval……）都会被
stmg/mod.py 的静态检查拦下来，包也发布不出去。

为什么这么严？因为美化包是「主题」，不是「引擎补丁」——
外观随便改，引擎一行都不许动。想改引擎行为请去改 stmg/ 里的源码。

数值说明：
    比例类     写 0~1 的小数（相对屏幕宽 / 高）
    颜色       写 (R, G, B) 或 (R, G, B, A)，取值 0~255
    图片/音乐  相对项目目录的路径，文件不存在会自动回退

能改的项和默认值全在 stmg/uiconf.py 的 DEFAULTS 里。下面是常用项，
想要哪项就把前面的 # 去掉再改（不写的项用引擎默认值）。
"""

CONFIG = {
    # ================ 对话框 ================
    # "box_x": 0.05,               # 左边距
    # "box_w": 0.90,               # 宽
    # "box_h": 0.28,               # 高
    # "box_radius": 14,            # 圆角
    # "box_color": (252, 250, 255),
    # "box_alpha": 224,            # 0~255，越小越透
    # "box_border": 2,
    # "box_border_color": (214, 176, 208),
    # "text_pad": 28,
    # "text_size": 23,

    # ================ 名字框 ================
    # "name_size": 22,
    # "name_bg": (226, 138, 178),
    # "name_color": (255, 255, 255),
    # "name_h": 0.075,

    # ================ 立绘 ================
    # "sprite_x": {"left": 0.24, "center": 0.5, "right": 0.76},
    # "sprite_w": 0.42,
    # "sprite_h": 0.76,
    # "sprite_bottom": 0.78,
    # "sprite_idle": True,         # 立绘轻微呼吸浮动
    # "sprite_idle_amp": 5,

    # ================ 标题界面 ================
    # "title_bg": "bg/title.png",  # 也可以指向美化包里的图：mod/<包名>/bg/bg.png
    # "title_bgm": "music/title.mp3",
    # "title_y": 0.18,
    # "title_size": 0.075,
    # "title_top": (46, 30, 52),
    # "title_bottom": (96, 62, 96),

    # ================ 选择支 ================
    # "choice_w": 0.54,
    # "choice_h": 56,
    # "choice_radius": 14,

    # ================ 打字机音效 ================
    # "type_se": "music/type.wav",
    # "type_se_volume": 0.4,
}
