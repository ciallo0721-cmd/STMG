#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""STMG 解包器 —— 把 stmenc/start.py 打出的发布版还原成游戏目录。

用法：

    python stmenc/unpack.py dist/我的游戏                    # 还原到 ./我的游戏_unpacked
    python stmenc/unpack.py dist/我的游戏 --out 还原目录
    python stmenc/unpack.py dist/我的游戏 --key 我的口令
    python stmenc/unpack.py dist/我的游戏 --force            # 目标目录已存在也照写
    python stmenc/unpack.py dist/我的游戏/assets.stmdec      # 只解单个资源包

口令来源（按优先级）：
    1. --key 参数
    2. 发布目录里 start.py 内嵌的 KEY（打包器就是这么写的）
    3. 环境变量 STMG_KEY

产物：
    script.stm / options.stm   ← 解密还原的剧本与配置
    bg/ png/ music/ ...        ← assets.stmdec 里逐个还原出来的素材
    解包报告.txt               ← 文件清单（加了什么、跳过了什么）

还原出的目录直接就能用引擎跑：python start.py 还原目录/script.stm

提醒：解包需要口令；口令本来就写在发布版 start.py 里，
这个工具是给「丢了解密前的原稿」的作者自己用的。
"""

import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from stmg import crypto                                        # noqa: E402

KEY_RE = re.compile(r"^KEY\s*=\s*(.+?)\s*$", re.M)


def key_from_startpy(start_py):
    """从发布版启动器里把 KEY 抠出来（eval 它的字面量，支持任意引号转义）。"""
    try:
        with open(start_py, "r", encoding="utf-8") as f:
            m = KEY_RE.search(f.read())
    except OSError:
        return None
    if not m:
        return None
    try:
        v = eval(m.group(1), {"__builtins__": {}})             # noqa: S307 - 字面量
        return v if isinstance(v, str) and v else None
    except Exception:                                          # noqa: BLE001
        return None


def resolve_key(target, args_key):
    if args_key:
        return args_key
    env = os.environ.get("STMG_KEY")
    if env:
        return env
    if os.path.isdir(target):
        cand = os.path.join(target, "start.py")
        if os.path.isfile(cand):
            k = key_from_startpy(cand)
            if k:
                return k
    return None


def safe_join(out, rel):
    """把包内相对路径落成真实路径，拦住 ../ 之类越界写法。"""
    rel = rel.replace("\\", "/")
    if rel.startswith("/") or ".." in rel.split("/"):
        raise ValueError("资源包里有可疑路径：%s" % rel)
    p = os.path.normpath(os.path.join(out, rel))
    if not p.startswith(os.path.normpath(out)):
        raise ValueError("资源包里有可疑路径：%s" % rel)
    return p


def write_file(path, data, report):
    if os.path.isfile(path):
        report.append("覆盖 " + os.path.relpath(path))
    else:
        report.append("写入 " + os.path.relpath(path))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def unpack_assets(assets_path, key, out, report):
    """解 assets.stmdec：按 JSON 索引把每个文件还原到 out 下。"""
    with open(assets_path, "rb") as f:
        raw = crypto.decrypt(f.read(), key)
    if len(raw) < 4:
        raise crypto.DecryptError("资源包是空的")
    hlen = struct.unpack(">I", raw[:4])[0]
    head = json.loads(raw[4:4 + hlen].decode("utf-8"))
    index = head.get("files", {})
    blob = raw[4 + hlen:]
    report.append("资源包 %s：%d 个文件" % (os.path.basename(assets_path), len(index)))
    for rel in sorted(index):
        item = index[rel]
        data = blob[item["o"]:item["o"] + item["n"]]
        write_file(safe_join(out, rel), data, report)
    return len(index)


def unpack_dir(src, key, out, force, report):
    """解整个发布目录：script / options / assets 全还原。"""
    did_assets = False
    script = os.path.join(src, "script.stmdec")
    if os.path.isfile(script):
        write_file(os.path.join(out, "script.stm"),
                   crypto.decrypt_file(script, key), report)
    else:
        report.append("跳过：目录里没有 script.stmdec")

    options = os.path.join(src, "options.stmdec")
    if os.path.isfile(options):
        write_file(os.path.join(out, "options.stm"),
                   crypto.decrypt_file(options, key), report)

    assets = os.path.join(src, "assets.stmdec")
    if os.path.isfile(assets):
        n = unpack_assets(assets, key, out, report)
        did_assets = n > 0

    report.append("素材包：%s" % ("已还原" if did_assets else "没有或为空"))
    return did_assets


def main(argv):
    args = argv[1:]
    if not args:
        print(__doc__)
        return 2

    target = os.path.abspath(args[0])
    out = None
    key_arg = None
    force = False

    i = 1
    while i < len(args):
        a = args[i]
        if a == "--out":
            i += 1
            out = args[i]
        elif a == "--key":
            i += 1
            key_arg = args[i]
        elif a == "--force":
            force = True
        i += 1

    if not os.path.exists(target):
        print("找不到：%s" % target)
        return 2

    key = resolve_key(target, key_arg)
    if not key:
        print("没找到口令。用 --key 指定，或确保发布目录里有内嵌 KEY 的 start.py，")
        print("或者设置环境变量 STMG_KEY。")
        return 2

    is_dir = os.path.isdir(target)
    default_out = (target if not is_dir else os.path.splitext(target)[0])
    out = os.path.abspath(out or default_out + "_unpacked")

    if os.path.isdir(out) and os.listdir(out) and not force:
        print("目标目录不是空的：%s" % out)
        print("换 --out 指定别的位置，或者加 --force 覆盖。")
        return 2
    os.makedirs(out, exist_ok=True)

    report = ["解包时间：源=%s" % target]
    try:
        if is_dir:
            unpack_dir(target, key, out, force, report)
        elif target.endswith(".stmdec"):
            if os.path.basename(target) == "assets.stmdec":
                unpack_assets(target, key, out, report)
            else:
                base = os.path.splitext(os.path.basename(target))[0]
                write_file(os.path.join(out, base),
                           crypto.decrypt_file(target, key), report)
        else:
            print("不认识的输入：%s（要发布目录或 .stmdec 文件）" % target)
            return 2
    except crypto.DecryptError as e:
        print("解密失败：%s" % e)
        print("检查口令是否正确。")
        return 3
    except (ValueError, KeyError, OSError) as e:
        print("解包出错：%s" % e)
        return 1

    # 解包报告落在输出目录里
    with open(os.path.join(out, "解包报告.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")

    print("解包完成：%s" % out)
    print("  还原 %d 项，明细见目录里的 解包报告.txt" % len(report))
    print("  试跑：python start.py %s" % os.path.join(out, "script.stm"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
