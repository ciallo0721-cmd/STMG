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
    pass


def _derive(password, salt, tag=b"enc"):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt + tag, ROUNDS, dklen=32)


def _keystream(key, nonce, length):
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hmac.new(key, nonce + counter.to_bytes(8, "big"),
                            hashlib.sha256).digest())
        counter += 1
    return bytes(out[:length])


def encrypt(plain, password):
    if isinstance(plain, str):
        plain = plain.encode("utf-8")
    salt = secrets.token_bytes(SALT_LEN)
    nonce = secrets.token_bytes(NONCE_LEN)
    key = _derive(password, salt, b"enc")
    mac_key = _derive(password, salt, b"mac")
    ct = bytes(a ^ b for a, b in zip(plain, _keystream(key, nonce, len(plain))))
    head = MAGIC + bytes([VERSION]) + salt + nonce + ct
    return head + hmac.new(mac_key, head, hashlib.sha256).digest()


def decrypt(blob, password):
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
    if not hmac.compare_digest(
            hmac.new(mac_key, body, hashlib.sha256).digest(), mac):
        raise DecryptError("校验失败：密钥不对，或者文件被人改过")
    key = _derive(password, salt, b"enc")
    ct = body[HEADER_LEN:]
    return bytes(a ^ b for a, b in zip(ct, _keystream(key, nonce, len(ct))))


def encrypt_file(src, dst, password):
    with open(src, "rb") as f:
        data = f.read()
    with open(dst, "wb") as f:
        f.write(encrypt(data, password))
    return os.path.getsize(dst)


def decrypt_file(src, password):
    with open(src, "rb") as f:
        return decrypt(f.read(), password)


def is_encrypted(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) == MAGIC
    except OSError:
        return False


def load_text(path, password=None, encoding="utf-8"):
    """读剧本：是 .stmdec 就解密，否则当普通 utf-8 文本读。"""
    if is_encrypted(path):
        if not password:
            raise DecryptError("%s 是加密包，但没有提供密钥" % os.path.basename(path))
        return decrypt_file(path, password).decode(encoding)
    with open(path, "r", encoding=encoding + "-sig") as f:
        return f.read()
