"""擴充點（CLAUDE.md §4.3）。各層只依賴這些介面，不依賴具體實作。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from usage_monitor.core.models import Usage


@dataclass(frozen=True)
class Token:
    """一個可用的 access token。`value` 不出現在 repr，避免意外進 log。"""

    value: str = field(repr=False)
    expires_at: datetime | None
    """UTC aware；None 表示來源沒提供到期時間。"""
    source: str
    """來源代碼，例如 "cli"、"desktop"；畫面依語言翻譯（core.i18n 的 source_*）。"""

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and self.expires_at <= now


@dataclass(frozen=True)
class Response:
    """Transport 回傳的 HTTP 回應（與 requests 無關，方便測試）。"""

    status: int
    headers: Mapping[str, str] = field(default_factory=dict[str, str])
    body: bytes = b""

    def header(self, name: str) -> str | None:
        """不分大小寫取 header。"""
        lowered = name.lower()
        for key, value in self.headers.items():
            if key.lower() == lowered:
                return value
        return None

    def json(self) -> Any:
        """解析 body；格式錯誤時丟 ValueError。"""
        return json.loads(self.body)


class Provider(Protocol):
    id: str
    """"claude"、"codex"。"""
    display_name: str
    """小工具上顯示的名稱。"""

    def poll(self) -> Usage:
        """取得最新用量；失敗時丟 PollError。"""
        ...

    def credential_signature(self) -> str:
        """憑證簽章；認證錯誤後簽章改變才恢復輪詢。"""
        ...

    def source_label(self) -> str | None:
        """目前使用的 token 來源代碼（例如 "desktop"），不含 token。"""
        ...


class CredentialSource(Protocol):
    name: str
    """來源代碼 "cli"、"desktop"、"codex_cli"。"""

    def read(self) -> Token | None:
        """讀取 token；任何失敗都回傳 None，不丟例外。"""
        ...

    def signature(self) -> str:
        """憑證內容的簽章，用來偵測重新登入。"""
        ...


class Transport(Protocol):
    """HTTP 傳輸。連線失敗或逾時時丟 PollError(ErrKind.TRANSIENT)。"""

    def get(self, url: str, headers: Mapping[str, str], timeout: float) -> Response: ...

    def post(self, url: str, headers: Mapping[str, str], json: Any, timeout: float) -> Response: ...


class Clock(Protocol):
    def now(self) -> datetime:
        """目前時間，UTC aware。"""
        ...
