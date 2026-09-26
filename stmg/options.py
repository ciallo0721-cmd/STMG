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
    # raw：先原样收集 <键, 值>，最后再统一映射到 opt（方便处理 Enc/Key 优先级等）
    raw = {}
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        # 空行和区块括号（<  >  </>）直接跳过，不是配置项
        if not s or s in ("<", ">", "</>"):
            continue
        m = re.match(r"^([A-Za-z_]\w*)\s*=\s*(.*)$", s)
        if not m:
            # 写歪了（不是「键 = 值」）记一笔，但不中断，其他项照常解析
            issues.append(Issue(n, "options 里这行看不懂：%s" % s[:30]))
            continue
        # 键统一小写（About / about 等价）
        k = m.group(1).lower()
        v = m.group(2).strip()
        # 值是被英文双引号包住的字符串字面量时，剥掉引号
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            v = v[1:-1]
        raw[k] = v

    opt["about"] = raw.get("about", "")
    # 口令优先级：Enc 优先于 Key（两者都写时以 Enc 为准）；都没写就是空（不加密）
    opt["enc"] = raw.get("enc", "") or raw.get("key", "")
    opt["key"] = raw.get("key", "")
    if raw.get("dec"):
        # 写了 dec：按逗号拆成 glob 列表（去掉首尾空格和空项）
        opt["dec"] = [x.strip() for x in raw["dec"].split(",") if x.strip()]
    else:
        # 没写 dec：给一套默认打包清单（剧本 + 常见素材类型）
        opt["dec"] = ["*.stm", "*.png", "*.jpg", "*.mp3", "*.wav", "*.ogg"]
    # 是否允许 R.api 联网：默认 true；写 false/0/no 才关（大小写不限）
    opt["allow_net"] = raw.get("allownet", "true").lower() not in ("false", "0", "no")
    # 语音自动挂载：AutoVoice = "true" 时，有角色名的台词按命名约定自动找配音
    opt["autovoice"] = raw.get("autovoice", "false").lower() in ("true", "1", "yes", "是")
    # 配音目录：默认 voice；用户写空串时用兜底 "voice"
    opt["voicedir"] = raw.get("voicedir", "voice").strip() or "voice"
    opt["_raw"] = raw
    opt["_issues"] = issues
    return opt


def load_options(path, key=None):
    """读 options。`.stmdec`（加密版）要用口令解开才能读；读不了时退回默认值不崩。"""
    # 路径为空或文件不存在：直接给默认配置（带空 issues 列表）
    if not path or not os.path.isfile(path):
        return dict(DEFAULTS, dec=list(DEFAULTS["dec"]), _issues=[])
    from . import crypto
    try:
        if crypto.is_encrypted(path):
            # 加密文件：用口令解密出明文
            text = crypto.load_text(path, key)
        else:
            # 普通文本：utf-8-sig 兼容带 BOM 的文件
            with open(path, "r", encoding="utf-8-sig") as f:
                text = f.read()
    except (crypto.DecryptError, OSError, UnicodeDecodeError) as e:
        # 口令错 / 文件坏 / 编码不对：不中断游戏，退回默认并记下原因
        return dict(DEFAULTS, dec=list(DEFAULTS["dec"]),
                    _issues=[Issue(None, "options 读不了：%s" % e)])
    # 先剥掉 HTML 风格注释 <!-- ... -->（跨行），再交给解析器
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
