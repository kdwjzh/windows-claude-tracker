"""真的呼叫 Windows DPAPI：先用 CryptProtectData 加密，再用程式的 dpapi_unprotect 解開。"""

from __future__ import annotations

import base64
import ctypes
import os
import sys

import pytest

from usage_monitor.platform import oscrypt

pytestmark = pytest.mark.windows


def _protect(data: bytes) -> bytes:
    assert sys.platform == "win32"
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = oscrypt._Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))  # pyright: ignore[reportPrivateUsage]
    blob_out = oscrypt._Blob()  # pyright: ignore[reportPrivateUsage]
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    assert ok
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def test_dpapi_roundtrip() -> None:
    secret = os.urandom(32)
    assert oscrypt.dpapi_unprotect(_protect(secret)) == secret


def test_unwrap_key_with_real_dpapi() -> None:
    key = os.urandom(32)
    encrypted = base64.b64encode(b"DPAPI" + _protect(key)).decode()
    assert oscrypt.unwrap_key(encrypted) == key


def test_dpapi_rejects_garbage() -> None:
    with pytest.raises(OSError):
        oscrypt.dpapi_unprotect(b"not dpapi data")
