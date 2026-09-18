#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""增量补丁工具（T5 / #14）。

对比「新项目」与「旧发布」，只把新增 / 改动过的资源打成一个加密补丁包，
并附一份含删减清单的 patch.json。复用 pack.build 的加密格式与口令，不自己发明加密。

用法：

    python tools/patch.py <项目> --old <旧发布目录或旧 assets.stmdec> \
        --out dist/补丁 [--key 口令]

产出到 --out：
    patch.stmdec   加密的补丁资源包（只含新增 / 改动的文件）
    patch.json     补丁索引（含 deleted 删减清单）

游戏侧：把这两个文件丢进发布目录，引擎启动时就会优先读补丁，无需重新打包整个游戏。
"""

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from stmg import crypto, options as optmod, pack                 # noqa: E402

DEFAULT_PATTERNS = ["*.png", "*.jpg", "*.jpeg", "*.webp",
                    "*.mp3", "*.wav", "*.ogg", "*.flac"]


def _load_old(old_arg, key):
    """返回 (old_index, old_data) —— 旧版本每个资源的 {rel: (hash16, size, bytes)}。

    old_arg 可以是：
      - 一个目录：里面找 assets.stmdec；
      - 一个 .stmdec 文件：直接当资源包读；
      - 不存在 / 找不到：当作空（即新项目里的全都是「新增」）。
    """
    stmdec = None
    if os.path.isfile(old_arg) and old_arg.lower().endswith(".stmdec"):
        stmdec = old_arg
    elif os.path.isdir(old_arg):
        cand = os.path.join(old_arg, "assets.stmdec")
        if os.path.isfile(cand):
            stmdec = cand

    out = {}
    if stmdec is None:
        return out

    try:
        pk = pack.AssetPack(stmdec, key)
    except crypto.DecryptError as e:
        raise SystemExit("读旧资源包失败（口令不对或文件损坏）：%s" % e)

    for rel in pk.names:
        try:
            data = pk.read(rel)
        except KeyError:
            continue
        # 老格式索引可能没有 hash 字段：现场算一个，保证比较能进行
        h = pk.index[rel].get("hash") or hashlib.sha256(data).hexdigest()[:16]
        out[rel] = (h, len(data), data)
    return out


def _scan_new(project, patterns):
    """扫描新项目，返回 {rel: (hash16, size, bytes)}。"""
    data = pack._scan(project, patterns)
    out = {}
    for rel, d in data.items():
        out[rel] = (hashlib.sha256(d).hexdigest()[:16], len(d), d)
    return out


def main(argv):
    args = argv[1:]
    if not args:
        print(__doc__)
        return 2

    project = os.path.abspath(args[0])
    old_arg = None
    out_dir = None
    key = None

    i = 1
    while i < len(args):
        a = args[i]
        if a == "--old":
            i += 1
            old_arg = args[i]
        elif a == "--out":
            i += 1
            out_dir = args[i]
        elif a == "--key":
            i += 1
            key = args[i]
        i += 1

    if not os.path.isdir(project):
        print("找不到项目目录：%s" % project)
        return 2
    if not old_arg:
        print("必须给 --old（旧发布目录或旧 assets.stmdec）。")
        return 2

    # 口令：优先命令行，否则读新项目 options.stm 的 Enc，再不行就空口令
    if key is None:
        opt = optmod.load_options(os.path.join(project, "options.stm"))
        key = opt.get("enc") or ""

    patterns = optmod.load_options(
        os.path.join(project, "options.stm")).get("dec") or DEFAULT_PATTERNS

    old = _load_old(old_arg, key)
    new = _scan_new(project, patterns)

    changed = {}        # rel -> bytes（新增或内容改动的）
    deleted = []        # 旧有但新版本里没了
    for rel, (nh, ns, nd) in new.items():
        if rel not in old or old[rel][0] != nh:
            changed[rel] = nd
    for rel in old:
        if rel not in new:
            deleted.append(rel)
    deleted.sort()

    if not changed and not deleted:
        print("新旧版本完全一致，没有需要打的补丁。")
        return 0

    out_dir = os.path.abspath(out_dir or os.path.join(ROOT, "dist", "patch"))
    if os.path.isdir(out_dir):
        # 只清掉上次的补丁产物，避免残留
        for fn in ("patch.stmdec", "patch.json"):
            p = os.path.join(out_dir, fn)
            if os.path.isfile(p):
                os.remove(p)
    os.makedirs(out_dir, exist_ok=True)

    patch_stmdec = os.path.join(out_dir, "patch.stmdec")
    patch_json = os.path.join(out_dir, "patch.json")

    if changed:
        n, size = pack.build_from_mapping(changed, patch_stmdec, key)
    else:
        # 纯删减补丁：资源包里一个文件都没有，仍然生成空包，保证格式一致
        n, size = pack.build_from_mapping({}, patch_stmdec, key)

    files_index = {}
    for rel, (nh, ns, _nd) in new.items():
        if rel in changed:
            files_index[rel] = {"hash": nh, "size": ns}

    with open(patch_json, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "patch": True,
                   "files": files_index, "deleted": deleted},
                  f, ensure_ascii=False, indent=2)

    print("补丁已生成：%s" % out_dir)
    print("  新增/改动 %d 个文件（%.1f KB），删减 %d 个文件"
          % (len(changed), size / 1024.0, len(deleted)))
    for rel in sorted(changed):
        print("    ~ %s" % rel)
    for rel in deleted:
        print("    - %s" % rel)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
