from __future__ import annotations

import base64
import os
import sys

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from usage_monitor.platform import oscrypt


def encrypt_v10(plain: bytes, key: bytes) -> str:
    nonce = os.urandom(12)
    return base64.b64encode(b"v10" + nonce + AESGCM(key).encrypt(nonce, plain, None)).decode()


def test_v10_roundtrip() -> None:
    key = os.urandom(32)
    assert oscrypt.decrypt_v10(encrypt_v10(b'{"a": 1}', key), key) == b'{"a": 1}'


def test_v10_wrong_key_raises_value_error() -> None:
    with pytest.raises(ValueError, match="AES-GCM"):
        oscrypt.decrypt_v10(encrypt_v10(b"x", os.urandom(32)), os.urandom(32))


@pytest.mark.parametrize(
    "blob",
    [
        b"v11" + b"\0" * 40,  # 錯誤前綴
        b"DPAPI" + b"\0" * 40,
        b"v10" + b"\0" * 20,  # 太短（< 3 + 12 + 16）
    ],
)
def test_v10_rejects_bad_blob(blob: bytes) -> None:
    with pytest.raises(ValueError):
        oscrypt.decrypt_v10(base64.b64encode(blob).decode(), os.urandom(32))


def test_v10_rejects_invalid_base64() -> None:
    with pytest.raises(ValueError, match="base64"):
        oscrypt.decrypt_v10("***", os.urandom(32))


def test_unwrap_key_strips_prefix_and_calls_unprotect() -> None:
    key = os.urandom(32)
    seen: list[bytes] = []

    def fake_unprotect(data: bytes) -> bytes:
        seen.append(data)
        return key

    encrypted = base64.b64encode(b"DPAPI" + b"wrapped").decode()
    assert oscrypt.unwrap_key(encrypted, fake_unprotect) == key
    assert seen == [b"wrapped"]


def test_unwrap_key_rejects_non_dpapi() -> None:
    with pytest.raises(ValueError, match="DPAPI"):
        oscrypt.unwrap_key(base64.b64encode(b"XXXXXkey").decode(), lambda d: d)


def test_unwrap_key_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="長度"):
        oscrypt.unwrap_key(base64.b64encode(b"DPAPIshort").decode(), lambda d: d)


@pytest.mark.skipif(sys.platform == "win32", reason="只測非 Windows 的錯誤路徑")
def test_dpapi_unavailable_off_windows() -> None:
    with pytest.raises(OSError):
        oscrypt.dpapi_unprotect(b"x")
