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


# --------------------------------------------------------------------------- #
# 成就系统（跨会话持久化）
# --------------------------------------------------------------------------- #
ACHIEVE_FILE = "achievements.json"


def load_achievements(root, title):
    """读某个剧本（按标题区分）已解锁的成就集合，读不到返回空集合。

    root 是项目目录，成就存在 <root>/.stmg_save/achievements.json 里，
    整体是个 {标题: [成就名...]} 的字典，所以可以一个存档目录容纳多款游戏。
    """
    p = os.path.join(save_dir(root), ACHIEVE_FILE)
    if not os.path.isfile(p):
        return set()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError):
        return set()
    names = data.get(title, [])
    return set(names) if isinstance(names, (list, tuple, set)) else set()


def save_achievements(root, title, names):
    """把某个剧本的已解锁成就集合写回 achievements.json。"""
    d = save_dir(root)
    p = os.path.join(d, ACHIEVE_FILE)
    data = {}
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (ValueError, OSError):
            data = {}
    if not isinstance(data, dict):
        data = {}
    data[title] = sorted(names)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except OSError:
        pass
