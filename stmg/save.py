# -*- coding: utf-8 -*-
"""存档槽读写。

存档不保存「引擎内部状态」，而是保存**玩家做过的所有选择** + 已经翻到第几句。
读档时从头重放，重放到同一个断点停下。
好处：不依赖 Runtime 的内部结构，改引擎也不会读不了老存档。
"""

import json
import os
import re
import time
import zipfile

SAVE_DIR = ".stmg_save"
SLOTS = 6

# 缩略图文件后缀：delete_slot 时一并清理（图片内容由 T3 用 pygame 写入，这里只管路径）
THUMB_SUFFIX = ".thumb.png"


def save_dir(root):
    d = os.path.join(root, SAVE_DIR)
    if not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    return d


def slot_path(root, n):
    return os.path.join(save_dir(root), "slot%d.json" % int(n))


def thumb_path(root, n):
    """<root>/.stmg_save/slot<N>.thumb.png —— 某个槽的缩略图绝对路径。"""
    return os.path.join(save_dir(root), "slot%d%s" % (int(n), THUMB_SUFFIX))


def has_thumb(root, n):
    """该槽有没有缩略图。"""
    return os.path.isfile(thumb_path(root, n))


def drop_thumb(root, n):
    """删掉该槽的缩略图（删档时一起调）。成功删除返回 True，没有 / 删失败返回 False。"""
    p = thumb_path(root, n)
    if os.path.isfile(p):
        try:
            os.remove(p)
            return True
        except OSError:
            return False
    return False


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
    ok = False
    if os.path.isfile(p):
        os.remove(p)
        ok = True
    # 顺手把缩略图也清掉，免得留个孤零零的 .thumb.png
    drop_thumb(root, n)
    return ok


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


# --------------------------------------------------------------------------- #
# CG 回廊（看过的背景 / 叠图，跨会话持久化）
# --------------------------------------------------------------------------- #
CG_FILE = "cg.json"


def load_cg(root, title):
    """读某个剧本已解锁的 CG 路径集合，读不到返回空集合。

    存在 <root>/.stmg_save/cg.json，结构和 achievements.json 一样：
    {标题: [路径...]}，一个存档目录可以容纳多款游戏。
    """
    p = os.path.join(save_dir(root), CG_FILE)
    if not os.path.isfile(p):
        return set()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError):
        return set()
    paths = data.get(title, [])
    return set(paths) if isinstance(paths, (list, tuple, set)) else set()


def save_cg(root, title, paths):
    """把某个剧本已解锁的 CG 集合写回 cg.json。"""
    d = save_dir(root)
    p = os.path.join(d, CG_FILE)
    data = {}
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (ValueError, OSError):
            data = {}
    if not isinstance(data, dict):
        data = {}
    data[title] = sorted(paths)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# 语言偏好（多语言剧本：script.stm + script.<lang>.stm）
# --------------------------------------------------------------------------- #
LANG_FILE = "lang.json"


def load_lang(root, title):
    """读某个剧本上次选的语言（空串 = 默认版 script.stm）。"""
    p = os.path.join(save_dir(root), LANG_FILE)
    if not os.path.isfile(p):
        return ""
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError):
        return ""
    v = data.get(title, "") if isinstance(data, dict) else ""
    return v if isinstance(v, str) else ""


def save_lang(root, title, lang):
    """记住某个剧本的语言选择。"""
    d = save_dir(root)
    p = os.path.join(d, LANG_FILE)
    data = {}
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (ValueError, OSError):
            data = {}
    if not isinstance(data, dict):
        data = {}
    data[title] = lang
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# 存档导入 / 导出（#6）
#
# 单个存档包格式 .stmgsav：一个 zip，里面是
#   manifest.json          {"format":1, "title":..., "engine":"STMG", "count":n}
#   slot1.json ... slot6.json   只含非空槽（槽号与存档目录里的文件名一致）
# 缩略图不进包（图片由 T3 运行时生成），导入导出只搬槽位的 JSON 数据。
# --------------------------------------------------------------------------- #
SLOT_FILE_RE = re.compile(r"^slot(\d+)\.json$")


def export_slots(root, title, out_path, slots=None):
    """把若干存档槽导出成一个 .stmgsav 包。

    root     项目目录（存档在 <root>/.stmg_save）
    title    游戏标题，写进 manifest
    out_path 导出的 .stmgsav 完整路径
    slots    None = 全部 6 个槽；否则给定槽号列表（如 [1,3]）

    返回 (ok, 消息)。没有任何非空槽时返回 (False, 原因)。
    """
    d = save_dir(root)
    if slots is None:
        candidates = list(range(1, SLOTS + 1))
    else:
        candidates = [int(x) for x in slots]
    planned = {}
    for n in candidates:
        snap = read_slot(root, n)
        if snap:                       # 空槽不进包
            planned[n] = snap
    if not planned:
        return (False, "没有可导出的存档（所有槽都是空的）")
    manifest = {"format": 1, "title": title, "engine": "STMG",
                "count": len(planned)}
    try:
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json",
                        json.dumps(manifest, ensure_ascii=False, indent=1))
            for n, snap in planned.items():
                zf.writestr("slot%d.json" % n,
                            json.dumps(snap, ensure_ascii=False, indent=1))
    except OSError as e:
        return (False, "导出失败：%s" % e)
    return (True, "已导出 %d 个存档到 %s" % (len(planned), out_path))


def import_slots(src_path, root, overwrite=True):
    """从 .stmgsav 导入存档槽。

    导入前会做完整校验：不是 zip / 缺 manifest / 不是 STMG 存档 / 槽文件非法，
    一律返回 (False, 原因, 0) 且**不写任何文件**（先在校验阶段把内容全读进内存）。
    校验通过后才落盘。slot 已存在且 overwrite=False 时跳过并计数。

    返回 (ok, 消息, 导入槽数)。
    """
    if not os.path.isfile(src_path):
        return (False, "找不到存档文件：%s" % src_path, 0)
    # 1) 先试着当 zip 打开，打不开说明不是合法存档包
    try:
        zf = zipfile.ZipFile(src_path, "r")
    except (zipfile.BadZipFile, OSError):
        return (False, "这不是合法的 STMG 存档包（zip 解不开）", 0)
    try:
        names = zf.namelist()
        # 2) 必须有 manifest.json，且是合法的 STMG 清单
        if "manifest.json" not in names:
            return (False, "存档包缺少 manifest.json", 0)
        try:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return (False, "manifest.json 不是合法 JSON", 0)
        if not isinstance(manifest, dict) or manifest.get("engine") != "STMG":
            return (False, "这不是 STMG 存档（engine 字段不符）", 0)
        # 3) 逐个槽文件：槽号必须在 1~SLOTS，且内容得是合法非空 JSON
        planned = {}        # n -> 原始字节
        for nm in names:
            m = SLOT_FILE_RE.match(nm)
            if not m:
                continue
            n = int(m.group(1))
            if n < 1 or n > SLOTS:
                continue
            try:
                raw = zf.read(nm)
                data = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return (False, "槽位文件 %s 不是合法 JSON" % nm, 0)
            if not isinstance(data, dict) or not data:
                continue    # 空槽不导入
            planned[n] = raw
    finally:
        zf.close()

    # 4) 校验全部通过，才真正落盘
    imported = 0
    for n, raw in planned.items():
        target = slot_path(root, n)
        if os.path.isfile(target) and not overwrite:
            continue
        try:
            with open(target, "wb") as f:
                f.write(raw)
        except OSError as e:
            return (False, "写入存档失败（槽 %d）：%s" % (n, e), imported)
        imported += 1
    return (True, "成功导入 %d 个存档槽" % imported, imported)
