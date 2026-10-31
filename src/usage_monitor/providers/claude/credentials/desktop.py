"""Claude 桌面版（Electron）的加密 token cache（CLAUDE.md §3.2）。

每個資料夾需要 `config.json`（加密的 token cache）與 `Local State`（加密的 AES 金鑰）。
任何讀檔或解密失敗都回傳 None 並記 debug log。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from usage_monitor.core.interfaces import Clock, Token
from usage_monitor.core.json_access import as_dict, as_str, parse_unix_ms
from usage_monitor.platform import oscrypt
from usage_monitor.providers.claude.credentials import desktop_paths
from usage_monitor.providers.claude.credentials.scopes import select_token

log = logging.getLogger(__name__)

SOURCE_NAME = "desktop"
CACHE_KEYS = ("oauth:tokenCacheV2", "oauth:tokenCache")
"""新的優先；遷移後舊 key 可能留下空字串，要跳過。"""


def _load_json(path: Path) -> dict[str, object] | None:
    try:
        return as_dict(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        log.debug("讀取 %s 失敗：%s", path.name, type(e).__name__)
        return None


def cache_values(config: dict[str, object]) -> list[tuple[str, str]]:
    """config.json 中非空的 token cache 密文，依優先順序。"""
    result: list[tuple[str, str]] = []
    for name in CACHE_KEYS:
        value = as_str(config.get(name))
        if value:
            result.append((name, value))
    return result


def read_key(directory: Path, unprotect: Callable[[bytes], bytes]) -> bytes | None:
    state = _load_json(directory / "Local State")
    encrypted = as_str((as_dict((state or {}).get("os_crypt")) or {}).get("encrypted_key"))
    if not encrypted:
        return None
    try:
        return oscrypt.unwrap_key(encrypted, unprotect)
    except (OSError, ValueError) as e:
        log.debug("%s 的 DPAPI 金鑰解不開：%s", directory.name, e)
        return None


def decrypt_entries(value: str, key: bytes) -> dict[str, object] | None:
    try:
        return as_dict(json.loads(oscrypt.decrypt_v10(value, key).decode("utf-8")))
    except (ValueError, UnicodeDecodeError) as e:
        log.debug("token cache 解密失敗：%s", e)
        return None


def read_dir(directory: Path, unprotect: Callable[[bytes], bytes]) -> Token | None:
    config = _load_json(directory / "config.json")
    if config is None:
        return None
    values = cache_values(config)
    if not values:
        return None
    key = read_key(directory, unprotect)
    if key is None:
        return None
    for name, value in values:
        entries = decrypt_entries(value, key)
        picked = select_token(entries) if entries else None
        if picked:
            log.debug("桌面版 token 來自 %s（%s）", directory.name, name)
            return Token(
                picked.token, expires_at=parse_unix_ms(picked.expires_at_ms), source=SOURCE_NAME
            )
    return None


class DesktopCredentialSource:
    name = SOURCE_NAME

    def __init__(
        self,
        clock: Clock,
        dirs: Callable[[], Sequence[Path]] = desktop_paths.data_dirs,
        unprotect: Callable[[bytes], bytes] = oscrypt.dpapi_unprotect,
    ) -> None:
        self._clock = clock
        self._dirs = dirs
        self._unprotect = unprotect

    def read(self) -> Token | None:
        """依序找各候選資料夾，回傳第一個未過期的 token；全都過期就回傳第一個找到的。"""
        now = self._clock.now()
        fallback: Token | None = None
        for directory in self._dirs():
            token = read_dir(directory, self._unprotect)
            if token is None:
                continue
            if not token.is_expired(now):
                return token
            fallback = fallback or token
        return fallback

    def signature(self) -> str:
        """比對 token cache 密文的 SHA-256。

        不用 config.json 的 mtime：桌面版會為了視窗位置等原因頻繁改寫這個檔案。
        """
        parts: list[str] = []
        for directory in self._dirs():
            config = _load_json(directory / "config.json") or {}
            digests = [
                f"{name}:{hashlib.sha256(value.encode()).hexdigest()[:16]}"
                for name, value in cache_values(config)
            ]
            parts.append(f"{directory}|{','.join(digests)}")
        return ";".join(parts)
