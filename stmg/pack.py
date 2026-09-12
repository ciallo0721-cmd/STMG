# -*- coding: utf-8 -*-
"""发布版的资源容器 `assets.stmdec`。

结构（加密之前的样子）：

    4 字节   头部 JSON 的长度（大端）
    N 字节   JSON：{"files": {"music/bgm.mp3": {"o": 偏移, "n": 长度}, ...}}
    余下     所有文件内容顺序拼在一起

整块再用 crypto.encrypt 加密。加载时一次性读进内存，之后按名字取字节流。
"""

import io
import json
import os
import struct

from . import crypto

PREFIX = "stmgpack:/"

_current = None


def set_current(pack):
    global _current
    _current = pack


def active():
    return _current


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


def build(root, patterns, out_path, key):
    """把 root 下匹配 patterns 的文件打包加密到 out_path。返回打包了几个文件。"""
    names = [p for p in _collect(root, patterns)
             if not p.endswith(".stmdec") and not p.startswith(".stmg_save/")]
    index, blob, off = {}, bytearray(), 0
    for rel in names:
        with open(os.path.join(root, rel), "rb") as f:
            data = f.read()
        index[rel] = {"o": off, "n": len(data)}
        blob.extend(data)
        off += len(data)
    head = json.dumps({"files": index}, ensure_ascii=False).encode("utf-8")
    raw = struct.pack(">I", len(head)) + head + bytes(blob)
    with open(out_path, "wb") as f:
        f.write(crypto.encrypt(raw, key))
    return len(names), os.path.getsize(out_path)


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
    """统一入口：真实文件 和 stmgpack:/... 都返回一个二进制文件对象。"""
    if is_pack_path(path):
        if _current is None:
            raise IOError("资源包没有加载")
        return io.BytesIO(_current.read(rel_of(path)))
    return open(path, "rb")


def exists(path):
    if not path:
        return False
    if is_pack_path(path):
        return _current is not None and _current.has(rel_of(path))
    return os.path.isfile(path)
