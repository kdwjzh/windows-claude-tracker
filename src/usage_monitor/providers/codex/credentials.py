"""Codex CLI 的 ChatGPT 帳號憑證：%CODEX_HOME%\\auth.json，未設定則 ~/.codex/auth.json。

只讀不寫；refresh_token 絕不使用。
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from usage_monitor.core.interfaces import Token
from usage_monitor.core.json_access import as_dict, as_str, parse_unix
from usage_monitor.platform import paths

log = logging.getLogger(__name__)

SOURCE_NAME = "codex_cli"


@dataclass(frozen=True)
class CodexAuth:
    token: Token
    account_id: str | None = field(default=None, repr=False)


def auth_path() -> Path:
    custom = os.environ.get("CODEX_HOME")
    return (Path(custom) if custom else paths.home() / ".codex") / "auth.json"


def jwt_expiry(token: str) -> object:
    """JWT payload 的 `exp`（Unix 秒）；不是 JWT 或解不開時回傳 None。只讀到期時間，不驗簽。"""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        data = as_dict(json.loads(base64.urlsafe_b64decode(payload)))
    except (binascii.Error, ValueError):
        return None
    return (data or {}).get("exp")


class CodexCredentialSource:
    name = SOURCE_NAME

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path or auth_path()

    def read_auth(self) -> CodexAuth | None:
        try:
            data: object = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            log.debug("Codex 憑證讀取失敗：%s", type(e).__name__)
            return None
        tokens = as_dict((as_dict(data) or {}).get("tokens"))
        if tokens is None:
            return None
        value = (as_str(tokens.get("access_token")) or "").strip()
        if not value:
            return None
        account_id = (as_str(tokens.get("account_id")) or "").strip() or None
        token = Token(value, expires_at=parse_unix(jwt_expiry(value)), source=self.name)
        return CodexAuth(token, account_id)

    def read(self) -> Token | None:
        auth = self.read_auth()
        return auth.token if auth else None

    def signature(self) -> str:
        p = self.path
        try:
            st = p.stat()
        except OSError:
            return f"{p}|missing"
        return f"{p}|{st.st_size}|{st.st_mtime_ns}"
