"""Claude 用量相關的 HTTP 呼叫與狀態碼分類（CLAUDE.md §3.3、§3.5）。"""

from __future__ import annotations

from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.interfaces import Response, Transport

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
MESSAGES_URL = "https://api.anthropic.com/v1/messages"
BETA = "oauth-2025-04-20"
API_VERSION = "2023-06-01"
PROBE_MODEL = "claude-haiku-4-5"
TIMEOUT = 30.0

RATELIMIT_PREFIX = "anthropic-ratelimit-unified-"


def retry_after(resp: Response) -> float | None:
    value = (resp.header("Retry-After") or "").strip()
    try:
        secs = float(value)
    except ValueError:
        return None
    return secs if secs >= 0 else None


def raise_for_status(resp: Response, what: str) -> None:
    """2xx 直接返回；其他依 §3.5 分類丟 PollError。"""
    status = resp.status
    if 200 <= status < 300:
        return
    if status in (401, 403):
        raise PollError(
            ErrKind.AUTH,
            f"{what}：登入被拒絕（HTTP {status}）",
            reason=ErrReason.REJECTED,
            status=status,
        )
    if status == 429 or status >= 500:
        raise PollError(
            ErrKind.TRANSIENT,
            f"{what}：伺服器暫時無法回應（HTTP {status}）",
            reason=ErrReason.RATE_LIMITED if status == 429 else ErrReason.SERVER,
            status=status,
            retry_after=retry_after(resp),
        )
    if 400 <= status < 500:
        raise PollError(
            ErrKind.UNSUPPORTED,
            f"{what}：不支援（HTTP {status}）",
            reason=ErrReason.UNSUPPORTED,
            status=status,
        )
    raise PollError(
        ErrKind.TRANSIENT,
        f"{what}：非預期的回應（HTTP {status}）",
        reason=ErrReason.BAD_RESPONSE,
        status=status,
    )


def get_usage(transport: Transport, token: str) -> Response:
    resp = transport.get(
        USAGE_URL,
        {"Authorization": f"Bearer {token}", "anthropic-beta": BETA},
        timeout=TIMEOUT,
    )
    raise_for_status(resp, "用量 API")
    return resp


def has_ratelimit_headers(resp: Response) -> bool:
    return any(k.lower().startswith(RATELIMIT_PREFIX) for k in resp.headers)


def probe_messages(transport: Transport, token: str) -> Response:
    """備援：送 1 token 的請求，用量資訊在 response header（會花一點額度）。

    就算回 429 也帶有 header，所以有 header 就直接用。
    """
    resp = transport.post(
        MESSAGES_URL,
        {
            "Authorization": f"Bearer {token}",
            "anthropic-version": API_VERSION,
            "anthropic-beta": BETA,
        },
        json={
            "model": PROBE_MODEL,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "."}],
        },
        timeout=TIMEOUT,
    )
    if resp.status in (401, 403) or not has_ratelimit_headers(resp):
        raise_for_status(resp, "Messages API")
        raise PollError(
            ErrKind.UNSUPPORTED,
            "Messages API 沒有回傳用量 header",
            reason=ErrReason.UNSUPPORTED,
            status=resp.status,
        )
    return resp
