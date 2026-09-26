# -*- coding: utf-8 -*-
"""`.stmdec` 加解密（纯标准库，零额外依赖）。

文件格式：

    偏移   长度   内容
    0      4      magic  b"STMG"
    4      1      版本号
    5      16     salt
    21     16     nonce
    37     N      密文
    37+N   32     HMAC-SHA256 校验值

密钥派生：PBKDF2-HMAC-SHA256(password, salt, 120000) -> 32 字节
密钥流  ：HMAC-SHA256(key, nonce || counter) 拼接后与明文异或
校验    ：HMAC-SHA256(mac_key, 前面所有字节)

⚠️ 说清楚：这不是强加密。
密钥和密文是一起发布给玩家的，愿意花时间的人一定能解开。
它的作用是「让玩家双击打不开、随手改不了」，**别拿它保护真密钥**。
"""

import hashlib
import hmac
import os
import secrets

MAGIC = b"STMG"
VERSION = 1
SALT_LEN = 16
NONCE_LEN = 16
MAC_LEN = 32
ROUNDS = 120000
HEADER_LEN = len(MAGIC) + 1 + SALT_LEN + NONCE_LEN


class DecryptError(Exception):
    """解密失败统一抛这个（文件不是 .stmdec / 版本不对 / 密钥错 / 被人改过）。"""
    pass


def _derive(password, salt, tag=b"enc"):
    """从同一个 password + salt 派生出一个 32 字节子密钥。

    tag 用来区分用途：b"enc" 派出来当加密密钥，b"mac" 派出来当校验密钥。
    两份子密钥彼此独立——即使把密文 XOR 出来也推导不出 MAC 密钥，反之亦然。
    120000 轮 PBKDF2 纯粹为了提高暴力破解的成本（见文件头 ROUNDS）。
    """
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt + tag, ROUNDS, dklen=32)


def _keystream(key, nonce, length):
    """造一段任意长度的「密钥流」——这就是整个加解密的核心。

    做法：以 key 为 HMAC 密钥，nonce 拼上递增的计数 counter 反复算
    HMAC-SHA256，把一个个 32 字节摘要首尾接起来，截到需要的长度。
    同一个 (key, nonce) 每次算出来都一模一样（所以解密端能还原），
    但内容对不知道 key 的人来说就是真随机噪声。明文和它逐字节 XOR 即加密。
    """
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hmac.new(key, nonce + counter.to_bytes(8, "big"),
                            hashlib.sha256).digest())
        counter += 1
    return bytes(out[:length])


def encrypt(plain, password):
    """把明文 plain（str 或 bytes）加密，返回完整的 .stmdec 字节包。

    每次都重新随机生成 salt 和 nonce——这样同一句话用同一密码加密，
    两次出来的字节也完全不同，别人没法靠「相同密文」推断「相同明文」。
    """
    if isinstance(plain, str):
        plain = plain.encode("utf-8")
    salt = secrets.token_bytes(SALT_LEN)       # 每次随机：抗重放/抗比对
    nonce = secrets.token_bytes(NONCE_LEN)
    key = _derive(password, salt, b"enc")
    mac_key = _derive(password, salt, b"mac")
    ct = bytes(a ^ b for a, b in zip(plain, _keystream(key, nonce, len(plain))))
    head = MAGIC + bytes([VERSION]) + salt + nonce + ct
    # 把「前面所有字节」的 HMAC 附在尾巴上，解密时用来验证密钥对 + 没被篡改
    return head + hmac.new(mac_key, head, hashlib.sha256).digest()


def decrypt(blob, password):
    """解密 .stmdec 字节包，返回明文 bytes。

    任何一道防线没过都抛 DecryptError：文件太短 / 魔数不对 / 版本不认 /
    密钥错导致 HMAC 校验失败（这里也覆盖「文件被改过」的情况）。
    """
    if len(blob) < HEADER_LEN + MAC_LEN:
        raise DecryptError("文件太短，不像是 .stmdec")
    if blob[:4] != MAGIC:
        raise DecryptError("文件头不对，不是 STMG 的加密包")
    ver = blob[4]
    if ver != VERSION:
        raise DecryptError("加密包版本 %d，这个引擎只认识 %d" % (ver, VERSION))
    salt = blob[5:5 + SALT_LEN]
    nonce = blob[5 + SALT_LEN:5 + SALT_LEN + NONCE_LEN]
    body, mac = blob[:-MAC_LEN], blob[-MAC_LEN:]
    mac_key = _derive(password, salt, b"mac")
    # 用 compare_digest 做**常量时间**比较，避免时序侧信道泄露密钥信息
    if not hmac.compare_digest(
            hmac.new(mac_key, body, hashlib.sha256).digest(), mac):
        raise DecryptError("校验失败：密钥不对，或者文件被人改过")
    key = _derive(password, salt, b"enc")
    ct = body[HEADER_LEN:]
    return bytes(a ^ b for a, b in zip(ct, _keystream(key, nonce, len(ct))))


def encrypt_file(src, dst, password):
    """把本地文件 src 加密写到 dst，返回 dst 的字节大小。"""
    with open(src, "rb") as f:
        data = f.read()
    with open(dst, "wb") as f:
        f.write(encrypt(data, password))
    return os.path.getsize(dst)                # 给上层显示「加密后多大」


def decrypt_file(src, password):
    """读本地 .stmdec 文件并解密，返回明文 bytes。"""
    with open(src, "rb") as f:
        return decrypt(f.read(), password)


def is_encrypted(path):
    """快速判断 path 是不是 .stmdec——只看前 4 字节魔数。

    读不到（文件不存在 / 没权限）一律当「不是加密包」返回 False，
    交给上层按普通文件处理或报错。
    """
    try:
        with open(path, "rb") as f:
            return f.read(4) == MAGIC
    except OSError:
        return False


def load_text(path, password=None, encoding="utf-8"):
    """统一读剧本入口：路径是 .stmdec 就解密，否则当普通文本读。

    encoding 默认 utf-8，且普通文本分支用 "utf-8-sig" 打开——
    顺手吃掉 Windows 记事本爱加的 BOM 头，免得第一行多出一个看不见的 ﻿。
    """
    if is_encrypted(path):
        if not password:
            raise DecryptError("%s 是加密包，但没有提供密钥" % os.path.basename(path))
        return decrypt_file(path, password).decode(encoding)
    with open(path, "r", encoding=encoding + "-sig") as f:
        return f.read()
