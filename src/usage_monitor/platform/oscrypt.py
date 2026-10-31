"""Chromium OSCrypt v10 解密（CLAUDE.md §3.2）：DPAPI 解出 AES 金鑰，再用 AES-256-GCM 解密。

失敗一律丟 ValueError 或 OSError，由呼叫端轉成「回傳 None」。
"""

from __future__ import annotations

import base64
import binascii
import ctypes
import sys
from collections.abc import Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DPAPI_PREFIX = b"DPAPI"
V10_PREFIX = b"v10"
NONCE_LEN = 12
TAG_LEN = 16


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def dpapi_unprotect(data: bytes) -> bytes:
    """以目前登入的 Windows 使用者身分解開 DPAPI 資料。"""
    if sys.platform != "win32":
        raise OSError("DPAPI 只能在 Windows 上使用")
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _b64decode(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError("不是合法的 base64") from e


def unwrap_key(
    encrypted_key_b64: str, unprotect: Callable[[bytes], bytes] = dpapi_unprotect
) -> bytes:
    """`Local State` 的 os_crypt.encrypted_key → 32 bytes AES 金鑰。"""
    raw = _b64decode(encrypted_key_b64)
    if not raw.startswith(DPAPI_PREFIX):
        raise ValueError("encrypted_key 不是 DPAPI 格式")
    key = unprotect(raw[len(DPAPI_PREFIX) :])
    if len(key) != 32:
        raise ValueError(f"AES 金鑰長度不對：{len(key)} bytes")
    return key


def decrypt_v10(value_b64: str, key: bytes) -> bytes:
    """`v10` + nonce(12) + 密文 + tag(16) → 明文。"""
    blob = _b64decode(value_b64)
    if not blob.startswith(V10_PREFIX):
        raise ValueError("不是 OSCrypt v10 格式")
    if len(blob) < len(V10_PREFIX) + NONCE_LEN + TAG_LEN:
        raise ValueError("OSCrypt v10 資料太短")
    nonce = blob[len(V10_PREFIX) : len(V10_PREFIX) + NONCE_LEN]
    try:
        return AESGCM(key).decrypt(nonce, blob[len(V10_PREFIX) + NONCE_LEN :], None)
    except InvalidTag as e:
        raise ValueError("AES-GCM 驗證失敗（金鑰與資料不是同一組）") from e
