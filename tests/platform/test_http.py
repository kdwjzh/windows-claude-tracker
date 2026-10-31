from __future__ import annotations

from typing import Any

import pytest
import requests

from usage_monitor.core.errors import ErrKind, PollError
from usage_monitor.platform.http import RequestsTransport


class StubSession(requests.Session):
    def __init__(self, result: requests.Response | BaseException) -> None:
        super().__init__()
        self.result = result
        self.kwargs: dict[str, Any] = {}

    def request(self, method: str | bytes, url: str | bytes, **kwargs: Any) -> requests.Response:  # type: ignore[override]
        self.kwargs = {"method": method, "url": url, **kwargs}
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def _response(status: int, body: bytes = b"{}", headers: dict[str, str] | None = None) -> Any:
    r = requests.Response()
    r.status_code = status
    r._content = body  # pyright: ignore[reportPrivateUsage]
    r.headers.update(headers or {})
    return r


def test_get_converts_response_and_disables_redirects() -> None:
    session = StubSession(_response(200, b'{"ok": 1}', {"Retry-After": "5"}))
    resp = RequestsTransport(session).get(
        "https://api.anthropic.com/api/oauth/usage", {"Authorization": "Bearer x"}, timeout=30
    )
    assert resp.status == 200
    assert resp.json() == {"ok": 1}
    assert resp.header("retry-after") == "5"
    assert session.kwargs["allow_redirects"] is False
    assert session.kwargs["timeout"] == 30
    assert session.headers["User-Agent"].startswith("usage-monitor/")


def test_post_sends_json() -> None:
    session = StubSession(_response(200))
    RequestsTransport(session).post("https://api.anthropic.com/v1/messages", {}, {"a": 1}, 30)
    assert session.kwargs["json"] == {"a": 1}


def test_token_only_sent_to_allowed_hosts() -> None:
    transport = RequestsTransport(StubSession(_response(200)))
    with pytest.raises(ValueError, match=r"evil\.example"):
        transport.get("https://evil.example/x", {"authorization": "Bearer x"}, timeout=30)
    with pytest.raises(ValueError, match="https"):
        transport.get("http://api.anthropic.com/x", {}, timeout=30)


@pytest.mark.parametrize(
    ("exc", "message"),
    [
        (requests.Timeout("secret url"), "連線逾時"),
        (requests.ConnectionError("Bearer sk-ant-secret"), "連線失敗：ConnectionError"),
    ],
)
def test_network_errors_become_transient_without_details(exc: BaseException, message: str) -> None:
    transport = RequestsTransport(StubSession(exc))
    with pytest.raises(PollError) as info:
        transport.get("https://api.anthropic.com/x", {}, timeout=30)
    assert info.value.kind is ErrKind.TRANSIENT
    assert info.value.message == message
    assert "secret" not in str(info.value)
