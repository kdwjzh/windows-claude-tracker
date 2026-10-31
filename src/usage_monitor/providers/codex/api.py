"""Codex 用量的 HTTP 呼叫與狀態碼分類（CLAUDE.md §3.4、§3.5）。

狀態碼分類與 Claude 相同；兩個服務互不 import（各自獨立），所以這裡有自己的一份。
"""

from __future__ import annotations

from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.interfaces import Response, Transport

USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
USER_AGENT = "codex-cli"
TIMEOUT = 30.0


def retry_after(resp: Response) -> float | None:
    value = (resp.header("Retry-After") or "").strip()
    try:
        secs = float(value)
    except ValueError:
        return None
    return secs if secs >= 0 else None


def raise_for_status(resp: Response) -> None:
    status = resp.status
    if 200 <= status < 300:
        return
    if status in (401, 403):
        raise PollError(
            ErrKind.AUTH,
            f"Codex 登入被拒絕（HTTP {status}）",
            reason=ErrReason.REJECTED,
            status=status,
        )
    if status == 429 or status >= 500:
        raise PollError(
            ErrKind.TRANSIENT,
            f"Codex 伺服器暫時無法回應（HTTP {status}）",
            reason=ErrReason.RATE_LIMITED if status == 429 else ErrReason.SERVER,
            status=status,
            retry_after=retry_after(resp),
        )
    if 400 <= status < 500:
        raise PollError(
            ErrKind.UNSUPPORTED,
            f"Codex 用量 API 不支援（HTTP {status}）",
            reason=ErrReason.UNSUPPORTED,
            status=status,
        )
    raise PollError(
        ErrKind.TRANSIENT,
        f"Codex 非預期的回應（HTTP {status}）",
        reason=ErrReason.BAD_RESPONSE,
        status=status,
    )


def get_usage(transport: Transport, token: str, account_id: str | None) -> Response:
    headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    resp = transport.get(USAGE_URL, headers, timeout=TIMEOUT)
    raise_for_status(resp)
    return resp
