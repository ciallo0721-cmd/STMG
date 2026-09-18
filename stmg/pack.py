# -*- coding: utf-8 -*-
"""发布版的资源容器 `assets.stmdec`。

结构（加密之前的样子）：

    4 字节   头部 JSON 的长度（大端）
    N 字节   JSON：{"files": {"music/bgm.mp3": {"o": 偏移, "n": 长度}, ...}}
    余下     所有文件内容顺序拼在一起

整块再用 crypto.encrypt 加密。加载时一次性读进内存，之后按名字取字节流。
"""

import hashlib
import io
import json
import os
import struct

from . import crypto

PREFIX = "stmgpack:/"

_current = None
# 补丁包：发布后下发的增量包（patch.stmdec）。存在时，open_binary / exists 优先用补丁，
# 没有补丁包时行为和老版本完全一致。
_patch = None
_patch_deleted = set()


def set_current(pack):
    global _current
    _current = pack


def active():
    return _current


def set_patch(pk):
    global _patch
    _patch = pk


def active_patch():
    return _patch


def set_patch_deleted(items):
    global _patch_deleted
    _patch_deleted = set(items or [])


def clear_patch():
    global _patch, _patch_deleted
    _patch = None
    _patch_deleted = set()


def apply_patch(root, key):
    """游戏启动时调用：若发布目录里存在补丁包（patch.stmdec / patch.json），
    就加载它，使资源读取优先走补丁。两者都不存在时等于什么都没做。"""
    stmdec = os.path.join(root, "patch.stmdec")
    if os.path.isfile(stmdec):
        try:
            set_patch(AssetPack(stmdec, key))
        except crypto.DecryptError:
            # 口令不对或文件损坏：安全降级，退回主资源包
            set_patch(None)
    jf = os.path.join(root, "patch.json")
    if os.path.isfile(jf):
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
            set_patch_deleted(data.get("deleted", []))
        except (ValueError, OSError):
            pass


def is_pack_path(path):
    return isinstance(path, str) and path.startswith(PREFIX)


def rel_of(path):
    return path[len(PREFIX):]


# --------------------------------------------------------------------------- #
def _collect(root, patterns):
    import fnmatch
    out = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            if any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(fn, p)
                   for p in patterns):
                out.append(rel)
    out.sort()
    return out


def _scan(root, patterns):
    """扫描 root 下匹配 patterns 的文件，返回 rel -> 原始字节。"""
    names = [p for p in _collect(root, patterns)
             if not p.endswith(".stmdec") and not p.startswith(".stmg_save/")]
    data = {}
    for rel in names:
        with open(os.path.join(root, rel), "rb") as f:
            data[rel] = f.read()
    return data


def build(root, patterns, out_path, key):
    """把 root 下匹配 patterns 的文件打包加密到 out_path。返回打包了几个文件。

    索引里每个资源都会记录 sha256（前 16 位够用）与 size；
    老版本产出的「无 hash 索引」资源包也能被 AssetPack 正常读取（向后兼容）。
    """
    return build_from_mapping(_scan(root, patterns), out_path, key)


def build_from_mapping(data, out_path, key):
    """从 {rel: 字节} 直接构建加密资源包（补丁工具复用同一套格式与密钥）。"""
    index, blob, off = {}, bytearray(), 0
    for rel in sorted(data):
        d = data[rel]
        index[rel] = {"o": off, "n": len(d),
                      "hash": hashlib.sha256(d).hexdigest()[:16],
                      "size": len(d)}
        blob.extend(d)
        off += len(d)
    head = json.dumps({"files": index}, ensure_ascii=False).encode("utf-8")
    raw = struct.pack(">I", len(head)) + head + bytes(blob)
    with open(out_path, "wb") as f:
        f.write(crypto.encrypt(raw, key))
    return len(index), os.path.getsize(out_path)


# --------------------------------------------------------------------------- #
class AssetPack(object):
    def __init__(self, path, key):
        self.path = path
        self.index = {}
        self.blob = b""
        with open(path, "rb") as f:
            raw = crypto.decrypt(f.read(), key)
        if len(raw) < 4:
            raise crypto.DecryptError("资源包是空的")
        hlen = struct.unpack(">I", raw[:4])[0]
        head = json.loads(raw[4:4 + hlen].decode("utf-8"))
        self.index = head.get("files", {})
        self.blob = raw[4 + hlen:]

    def has(self, rel):
        return rel in self.index

    def read(self, rel):
        item = self.index.get(rel)
        if not item:
            raise KeyError(rel)
        return self.blob[item["o"]:item["o"] + item["n"]]

    @property
    def names(self):
        return sorted(self.index.keys())

    def __len__(self):
        return len(self.index)


# --------------------------------------------------------------------------- #
def open_binary(path):
    """统一入口：真实文件 和 stmgpack:/... 都返回一个二进制文件对象。

    存在补丁包时，补丁里的资源优先；被补丁标记为删除的资源会直接报错；
    其余回退到主资源包。没有补丁包时行为与老版本完全一致。
    """
    if is_pack_path(path):
        if _current is None and _patch is None:
            raise IOError("资源包没有加载")
        rel = rel_of(path)
        if _patch is not None and _patch.has(rel):
            return io.BytesIO(_patch.read(rel))
        if rel in _patch_deleted:
            raise IOError("资源已被补丁删除：%s" % rel)
        if _current is None:
            raise IOError("资源包没有加载：%s" % rel)
        return io.BytesIO(_current.read(rel))
    return open(path, "rb")


def exists(path):
    if not path:
        return False
    if is_pack_path(path):
        rel = rel_of(path)
        if _patch is not None and _patch.has(rel):
            return True
        if rel in _patch_deleted:
            return False
        return _current is not None and _current.has(rel)
    return os.path.isfile(path)
