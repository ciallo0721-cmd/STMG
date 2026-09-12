# -*- coding: utf-8 -*-
"""存档槽读写。

存档不保存「引擎内部状态」，而是保存**玩家做过的所有选择** + 已经翻到第几句。
读档时从头重放，重放到同一个断点停下。
好处：不依赖 Runtime 的内部结构，改引擎也不会读不了老存档。
"""

import json
import os
import time

SAVE_DIR = ".stmg_save"
SLOTS = 6


def save_dir(root):
    d = os.path.join(root, SAVE_DIR)
    if not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    return d


def slot_path(root, n):
    return os.path.join(save_dir(root), "slot%d.json" % int(n))


def write_slot(root, n, snap):
    snap = dict(snap)
    snap["time"] = time.strftime("%Y-%m-%d %H:%M")
    with open(slot_path(root, n), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    return snap


def read_slot(root, n):
    p = slot_path(root, n)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return None


def list_slots(root):
    out = []
    for i in range(1, SLOTS + 1):
        out.append(read_slot(root, i))
    return out


def delete_slot(root, n):
    p = slot_path(root, n)
    if os.path.isfile(p):
        os.remove(p)
        return True
    return False


def describe(snap):
    if not snap:
        return "空档"
    tail = snap.get("history_tail") or []
    snippet = ""
    if tail:
        snippet = tail[-1][1] if isinstance(tail[-1], (list, tuple)) else str(tail[-1])
    snippet = snippet.replace("\n", " ")[:18]
    return "%s  %s" % (snap.get("time", "?"), snippet)
