# -*- coding: utf-8 -*-
"""options.stm 解析。

设计稿里的样子：

    <
    About = "这里是显示在 about 中的内容"
    Enc   = "这里是密钥"
    dec   = "*.stm,*.png,*.txt"
    Key   = "132456789"
    >

补充约定：
  * `Enc`（或 `Key`）—— 加密 / 解密用的口令，两个都写时以 Enc 为准
  * `dec`            —— 加密时打包哪些文件，逗号分隔的 glob
  * `About`          —— 「关于」界面里显示的文字
  * `AllowNet`       —— 发布版要不要允许 R.api 联网，默认 true
"""

import os
import re

from .errors import Issue


DEFAULTS = {
    "about": "",
    "enc": "",
    "key": "",
    "dec": [],
    "allow_net": True,
    "autovoice": False,
    "voicedir": "voice",
}


def parse_options_text(text, path="<memory>"):
    opt = dict(DEFAULTS)
    issues = []
    raw = {}
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s in ("<", ">", "</>"):
            continue
        m = re.match(r"^([A-Za-z_]\w*)\s*=\s*(.*)$", s)
        if not m:
            issues.append(Issue(n, "options 里这行看不懂：%s" % s[:30]))
            continue
        k = m.group(1).lower()
        v = m.group(2).strip()
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            v = v[1:-1]
        raw[k] = v

    opt["about"] = raw.get("about", "")
    opt["enc"] = raw.get("enc", "") or raw.get("key", "")
    opt["key"] = raw.get("key", "")
    if raw.get("dec"):
        opt["dec"] = [x.strip() for x in raw["dec"].split(",") if x.strip()]
    else:
        opt["dec"] = ["*.stm", "*.png", "*.jpg", "*.mp3", "*.wav", "*.ogg"]
    opt["allow_net"] = raw.get("allownet", "true").lower() not in ("false", "0", "no")
    # 语音自动挂载：AutoVoice = "true" 时，有角色名的台词按命名约定自动找配音
    opt["autovoice"] = raw.get("autovoice", "false").lower() in ("true", "1", "yes", "是")
    opt["voicedir"] = raw.get("voicedir", "voice").strip() or "voice"
    opt["_raw"] = raw
    opt["_issues"] = issues
    return opt


def load_options(path, key=None):
    """读 options。`.stmdec` 的要用口令解开才能读。"""
    if not path or not os.path.isfile(path):
        return dict(DEFAULTS, dec=list(DEFAULTS["dec"]), _issues=[])
    from . import crypto
    try:
        if crypto.is_encrypted(path):
            text = crypto.load_text(path, key)
        else:
            with open(path, "r", encoding="utf-8-sig") as f:
                text = f.read()
    except (crypto.DecryptError, OSError, UnicodeDecodeError) as e:
        return dict(DEFAULTS, dec=list(DEFAULTS["dec"]),
                    _issues=[Issue(None, "options 读不了：%s" % e)])
    text = re.sub(r"<--.*?-->", "", text, flags=re.S)
    return parse_options_text(text, path)


def find_options(script_path):
    """在剧本同级找 options.stm / options.stmdec。"""
    d = os.path.dirname(os.path.abspath(script_path))
    for name in ("options.stm", "options.stmdec"):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return ""
