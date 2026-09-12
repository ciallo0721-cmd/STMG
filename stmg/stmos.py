# -*- coding: utf-8 -*-
"""stm.os —— 受控的文件系统操作（DDLC 式彩蛋用）。

只暴露 4 个动作，全部走「看起来像正常游戏功能」的接口，不暴露 Python
运行时，避免在发布版里「穿帮」：

    read     读文件，内容进 STM.OS
    create   建一个空文件（已存在则不动）
    remove   移到回收站（不是永久删除，能找回）
    revision 改文件，先留 .bak 备份再替换

安全兜底（这是和 STM.python 最大的区别，也是它能藏住的原因）：
  * remove 永远走回收站，误删可找回，绝不做永久删除 / 递归删除。
  * revision 永远先留 filename.后缀.bak，改坏了能还原。
  * 不做格式化、不碰系统目录——这里只管「读 / 建 / 移回收站 / 改 + 备份」。

注意：这本质是读写玩家机器上的文件。请只用于自己电脑上的演示，
或玩家明确知情同意的演出（比如读写游戏自己的存档目录）。
"""

import os
import shutil
import sys


# --------------------------------------------------------------------------- #
# 对外动作
# --------------------------------------------------------------------------- #
def read_file(path):
    """读文件，返回 (ok, 内容字符串)。打不开返回 (False, "")。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return True, f.read()
    except Exception:
        return False, ""


def create_file(path):
    """建一个空文件。已存在则不动，返回 (ok, 消息)。"""
    try:
        if os.path.exists(path):
            return True, "已存在，未改动"
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with open(path, "w", encoding="utf-8") as f:
            pass
        return True, ""
    except Exception as e:                       # noqa: BLE001
        return False, "%s: %s" % (type(e).__name__, e)


def remove_file(path):
    """删文件，但**移进回收站**而不是永久删除。返回 (ok, 消息)。"""
    if not os.path.exists(path):
        return True, "不存在，跳过"
    try:
        if send_to_trash(path):
            return True, ""
        return False, "移回收站失败"
    except Exception as e:                       # noqa: BLE001
        return False, "%s: %s" % (type(e).__name__, e)


def revision_file(path, old, new):
    """改文件，先留 .bak 备份。返回 (ok, 消息)。

    两种用法：
      * old 非空：把文件里**所有** old 替换成 new（经典替换）
      * old 为空：把**整个文件内容**直接设成 new（相当于写入 / 覆盖）
    两种情况都会先复制一份 filename.后缀.bak。
    """
    if old is None or new is None:
        return False, "revision 需要 ,\"旧内容\"to\"新内容\""
    if not os.path.exists(path):
        return False, "文件不存在"
    try:
        bak = path + ".bak"
        shutil.copy2(path, bak)
        if old:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
            data = data.replace(old, new)
        else:
            data = new
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
        return True, ""
    except Exception as e:                       # noqa: BLE001
        return False, "%s: %s" % (type(e).__name__, e)


# --------------------------------------------------------------------------- #
# 回收站（跨平台）
# --------------------------------------------------------------------------- #
def send_to_trash(path):
    """把文件 / 目录移到系统回收站。成功返回 True。"""
    if sys.platform.startswith("win"):
        return _win_trash(path)
    if sys.platform == "darwin":
        return _mac_trash(path)
    return _linux_trash(path)


def _win_trash(path):
    """Windows：用 SHFileOperationW 的 FO_DELETE + FOF_ALLOWUNDO 移进回收站。"""
    try:
        import ctypes
        from ctypes import (Structure, byref, create_unicode_buffer,
                            wintypes)
    except Exception:                            # noqa: BLE001
        return _fallback_trash(path)
    try:
        class SHFILEOPSTRUCTW(Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", wintypes.UINT),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", wintypes.LPVOID),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        FO_DELETE = 3
        FOF_ALLOWUNDO = 0x40        # 移回收站
        FOF_NOCONFIRMATION = 0x10   # 不弹确认框
        FOF_SILENT = 0x4
        FOF_NOERRORUI = 0x400

        # pFrom 需要双 null 结尾
        src = create_unicode_buffer(path + "\0\0")
        op = SHFILEOPSTRUCTW(
            0, FO_DELETE, src, None,
            FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI,
            0, None, None)
        res = ctypes.windll.shell32.SHFileOperationW(byref(op))
        if res == 0 and not op.fAnyOperationsAborted:
            return True
        return _fallback_trash(path)
    except Exception:                            # noqa: BLE001
        return _fallback_trash(path)


def _mac_trash(path):
    """macOS：mv 到 ~/.Trash。"""
    try:
        trash = os.path.expanduser("~/.Trash")
        os.makedirs(trash, exist_ok=True)
        dest = os.path.join(trash, os.path.basename(path))
        if os.path.exists(dest):
            dest += ".stm"
        shutil.move(path, dest)
        return True
    except Exception:                            # noqa: BLE001
        return _fallback_trash(path)


def _linux_trash(path):
    """Linux：优先 gio trash，失败退回 ~/.local/share/Trash。"""
    try:
        import subprocess
        subprocess.run(["gio", "trash", path], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:                            # noqa: BLE001
        try:
            trash = os.path.join(os.path.expanduser("~"),
                                 ".local", "share", "Trash", "files")
            os.makedirs(trash, exist_ok=True)
            dest = os.path.join(trash, os.path.basename(path))
            if os.path.exists(dest):
                dest += ".stm"
            shutil.move(path, dest)
            return True
        except Exception:                        # noqa: BLE001
            return _fallback_trash(path)


def _fallback_trash(path):
    """兜底：移到用户目录下的 .stm_os_trash，绝不永久删除。"""
    try:
        box = os.path.join(os.path.expanduser("~"), ".stm_os_trash")
        os.makedirs(box, exist_ok=True)
        dest = os.path.join(box, os.path.basename(path))
        if os.path.exists(dest):
            dest += ".stm"
        if os.path.isdir(path):
            shutil.copytree(path, dest)
            shutil.rmtree(path, ignore_errors=True)
        else:
            shutil.move(path, dest)
        return True
    except Exception:                            # noqa: BLE001
        return False
