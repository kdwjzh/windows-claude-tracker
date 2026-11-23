"""Antigravity 本機 language server 的 Connect-RPC 呼叫（CLAUDE.md §3.10）。

只連 127.0.0.1；csrf token 放在 `X-Codeium-Csrf-Token`，不用任何 Google 登入 token。
"""

from __future__ import annotations

from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.interfaces import Response, Transport
from usage_monitor.providers.antigravity.hub import Hub

SERVICE = "exa.language_server_pb.LanguageServerService"
TIMEOUT = 30.0


def url(hub: Hub, method: str) -> str:
    return f"http://127.0.0.1:{hub.port}/{SERVICE}/{method}"


def raise_for_status(resp: Response) -> None:
    status = resp.status
    if 200 <= status < 300:
        return
    if status in (401, 403):
        # csrf token 不對：通常是 Antigravity 重開後 hub 檔還沒換
        raise PollError(
            ErrKind.AUTH,
            f"Antigravity 拒絕連線（HTTP {status}）",
            reason=ErrReason.REJECTED,
            status=status,
        )
    raise PollError(
        ErrKind.TRANSIENT,
        f"Antigravity 非預期的回應（HTTP {status}）",
        reason=ErrReason.SERVER if status >= 500 else ErrReason.BAD_RESPONSE,
        status=status,
    )


def call(transport: Transport, hub: Hub, method: str) -> Response:
    headers = {"Content-Type": "application/json", "X-Codeium-Csrf-Token": hub.csrf_token}
    resp = transport.post(url(hub, method), headers, {}, timeout=TIMEOUT)
    raise_for_status(resp)
    return resp
