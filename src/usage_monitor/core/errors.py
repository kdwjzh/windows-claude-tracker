"""輪詢錯誤的分類（CLAUDE.md §3.5）。

例外訊息會進 log 與懸停卡，**絕對不可以含 token**。
"""

from __future__ import annotations

from enum import Enum


class ErrKind(Enum):
    AUTH = "auth"
    """找不到 token、token 過期、HTTP 401／403：暫停輪詢，等憑證簽章改變。"""

    TRANSIENT = "transient"
    """HTTP 429／5xx、連線失敗、逾時、格式錯誤：指數退避後重試。"""

    UNSUPPORTED = "unsupported"
    """其他 4xx：端點不支援，由 provider 決定是否改走備援。"""


class ErrReason(Enum):
    """錯誤的具體原因，給畫面翻成當前語言（CLAUDE.md §3.8）；`message` 只給 log。"""

    NO_CREDENTIALS = "no_credentials"
    EXPIRED = "expired"
    REJECTED = "rejected"
    """HTTP 401／403。"""
    RATE_LIMITED = "rate_limited"
    """HTTP 429。"""
    SERVER = "server"
    """HTTP 5xx。"""
    NETWORK = "network"
    TIMEOUT = "timeout"
    UNSUPPORTED = "unsupported"
    BAD_RESPONSE = "bad_response"
    """格式錯誤、沒有任何用量視窗、非預期的狀態碼。"""
    UNEXPECTED = "unexpected"
    """程式沒預料到的例外。"""


class PollError(Exception):
    """provider.poll() 失敗時丟出的唯一例外型別。"""

    def __init__(
        self,
        kind: ErrKind,
        message: str,
        *,
        reason: ErrReason | None = None,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.reason = reason
        """None 時畫面退回顯示 message（舊程式或測試）。"""
        self.status = status
        self.retry_after = retry_after
        """伺服器要求的等待秒數（`Retry-After`）；沒有則為 None。"""

    def __repr__(self) -> str:
        reason = f", reason={self.reason.name}" if self.reason else ""
        return f"PollError({self.kind.name}, {self.message!r}, status={self.status}{reason})"
