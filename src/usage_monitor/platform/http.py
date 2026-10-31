"""requests 實作的 Transport。

安全：token 只能送到 api.anthropic.com 與 chatgpt.com（CLAUDE.md §5.1 第 4 條），
帶 Authorization 的請求送往其他主機會直接拒絕；也不跟隨轉址，避免 token 被帶到別處。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import requests

from usage_monitor import __version__
from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.interfaces import Response

ALLOWED_HOSTS = frozenset({"api.anthropic.com", "chatgpt.com"})
USER_AGENT = f"usage-monitor/{__version__}"


def inject_truststore() -> None:
    """改用 Windows 憑證庫驗證 SSL（公司網路有 SSL 檢查時需要）。程式啟動時呼叫一次。"""
    try:
        import truststore
    except ImportError:  # pragma: no cover - 依賴一定會裝
        return
    truststore.inject_into_ssl()


def _check_destination(url: str, headers: Mapping[str, str]) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise ValueError(f"只允許 https：{parts.scheme}")
    has_auth = any(k.lower() == "authorization" for k in headers)
    if has_auth and parts.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"不允許把 token 送到 {parts.hostname}")


class RequestsTransport:
    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT

    def get(self, url: str, headers: Mapping[str, str], timeout: float) -> Response:
        return self._request("GET", url, headers, None, timeout)

    def post(self, url: str, headers: Mapping[str, str], json: Any, timeout: float) -> Response:
        return self._request("POST", url, headers, json, timeout)

    def _request(
        self, method: str, url: str, headers: Mapping[str, str], json: Any, timeout: float
    ) -> Response:
        _check_destination(url, headers)
        try:
            r = self._session.request(
                method, url, headers=dict(headers), json=json, timeout=timeout,
                allow_redirects=False,
            )  # fmt: skip
        except requests.Timeout as e:
            raise PollError(ErrKind.TRANSIENT, "連線逾時", reason=ErrReason.TIMEOUT) from e
        except requests.RequestException as e:
            # 例外訊息可能含 URL 或 header，只留型別名稱
            raise PollError(
                ErrKind.TRANSIENT, f"連線失敗：{type(e).__name__}", reason=ErrReason.NETWORK
            ) from e
        return Response(status=r.status_code, headers=dict(r.headers), body=r.content)
