"""建立假的 Claude 桌面版資料夾：測試內自產金鑰加密，DPAPI 用 `identity`（直接回傳）。"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_PREFIX = "inst:user:https://api.anthropic.com"


def identity(data: bytes) -> bytes:
    """假 DPAPI：Local State 裡直接放明文金鑰。"""
    return data


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def encrypt_entries(entries: dict[str, object], key: bytes) -> str:
    nonce = os.urandom(12)
    plain = json.dumps(entries).encode()
    return base64.b64encode(b"v10" + nonce + AESGCM(key).encrypt(nonce, plain, None)).decode()


def make_dir(
    path: Path,
    entries: dict[str, object] | None = None,
    *,
    key: bytes | None = None,
    cache_key: str = "oauth:tokenCacheV2",
    extra: dict[str, object] | None = None,
) -> Path:
    key = key or os.urandom(32)
    path.mkdir(parents=True, exist_ok=True)
    (path / "Local State").write_text(
        json.dumps({"os_crypt": {"encrypted_key": base64.b64encode(b"DPAPI" + key).decode()}}),
        encoding="utf-8",
    )
    config: dict[str, object] = {"windowState": {"x": 1}, **(extra or {})}
    if entries is not None:
        config[cache_key] = encrypt_entries(entries, key)
    (path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return path


def entry(
    token: str, expires: datetime, scopes: str = "user:inference user:profile"
) -> dict[str, object]:
    return {f"{KEY_PREFIX}:{scopes}": {"token": token, "expiresAt": _ms(expires)}}
