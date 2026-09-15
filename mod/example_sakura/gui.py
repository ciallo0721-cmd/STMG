# -*- coding: utf-8 -*-
"""「樱花飘落」示例美化包 —— 桌面端外观参数。

想看效果：

    python start.py demo/script.stm --mod example_sakura

想改成自己的主题，直接改下面的数字；每项的含义和取值范围见
stmg/uiconf.py 的 DEFAULTS（那里是引擎默认值，这里没写到的项就跟着它走）。

注意：这个文件只能声明 CONFIG 字典，不能写代码。想在网页版加点动效，
去 theme.js；想改网页版样式，去 theme.css。
"""

CONFIG = {
    # ---- 对话框：粉白、圆一点、透一点点 ----
    "box_h": 0.28,
    "box_radius": 16,
    "box_color": (255, 248, 252),
    "box_alpha": 228,
    "box_border": 2,
    "box_border_color": (240, 188, 214),
    "text_pad": 30,

    # ---- 名字框：樱花粉 ----
    "name_bg": (226, 138, 178),
    "name_h": 0.072,

    # ---- 立绘：轻微呼吸浮动 ----
    "sprite_idle": True,
    "sprite_idle_amp": 5,

    # ---- 标题界面：紫粉渐变 ----
    "title_top": (58, 34, 58),
    "title_bottom": (122, 72, 110),

    # ---- 选择支：圆角大一点 ----
    "choice_h": 56,
    "choice_radius": 14,
}
