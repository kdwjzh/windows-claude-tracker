from __future__ import annotations

import pytest

from fakes import FakeTransport
from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.interfaces import Response
from usage_monitor.providers.claude import api


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (401, ErrKind.AUTH),
        (403, ErrKind.AUTH),
        (429, ErrKind.TRANSIENT),
        (500, ErrKind.TRANSIENT),
        (503, ErrKind.TRANSIENT),
        (404, ErrKind.UNSUPPORTED),
        (400, ErrKind.UNSUPPORTED),
        (302, ErrKind.TRANSIENT),
    ],
)
def test_status_classification(status: int, kind: ErrKind) -> None:
    with pytest.raises(PollError) as info:
        api.raise_for_status(Response(status), "測試")
    assert info.value.kind is kind
    assert info.value.status == status


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (401, ErrReason.REJECTED),
        (429, ErrReason.RATE_LIMITED),
        (502, ErrReason.SERVER),
        (404, ErrReason.UNSUPPORTED),
        (302, ErrReason.BAD_RESPONSE),
    ],
)
def test_status_reason(status: int, reason: ErrReason) -> None:
    with pytest.raises(PollError) as info:
        api.raise_for_status(Response(status), "測試")
    assert info.value.reason is reason


@pytest.mark.parametrize("status", [200, 204])
def test_success_does_not_raise(status: int) -> None:
    api.raise_for_status(Response(status), "測試")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("120", 120.0), ("1.5", 1.5), ("-1", None), ("soon", None), (None, None)],
)
def test_retry_after(value: str | None, expected: float | None) -> None:
    headers = {"Retry-After": value} if value is not None else {}
    assert api.retry_after(Response(429, headers)) == expected


def test_429_carries_retry_after() -> None:
    with pytest.raises(PollError) as info:
        api.raise_for_status(Response(429, {"retry-after": "60"}), "測試")
    assert info.value.retry_after == 60


def test_get_usage_sends_expected_headers() -> None:
    transport = FakeTransport().add("GET", api.USAGE_URL, Response(200, body=b"{}"))
    api.get_usage(transport, "tok")
    call = transport.calls[0]
    assert call.headers == {"Authorization": "Bearer tok", "anthropic-beta": "oauth-2025-04-20"}
    assert call.timeout == 30


def test_probe_messages_request_shape() -> None:
    resp = Response(200, {"anthropic-ratelimit-unified-5h-utilization": "0.1"})
    transport = FakeTransport().add("POST", api.MESSAGES_URL, resp)
    assert api.probe_messages(transport, "tok") is resp
    call = transport.calls[0]
    assert call.json == {
        "model": "claude-haiku-4-5",
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "."}],
    }
    assert call.headers["anthropic-version"] == "2023-06-01"
    assert call.headers["Authorization"] == "Bearer tok"


def test_probe_messages_429_with_headers_is_usable() -> None:
    resp = Response(429, {"anthropic-ratelimit-unified-status": "rejected"})
    transport = FakeTransport().add("POST", api.MESSAGES_URL, resp)
    assert api.probe_messages(transport, "tok") is resp


@pytest.mark.parametrize(
    ("resp", "kind"),
    [
        (Response(401, {"anthropic-ratelimit-unified-status": "allowed"}), ErrKind.AUTH),
        (Response(200), ErrKind.UNSUPPORTED),
        (Response(400), ErrKind.UNSUPPORTED),
        (Response(529), ErrKind.TRANSIENT),
    ],
)
def test_probe_messages_errors(resp: Response, kind: ErrKind) -> None:
    transport = FakeTransport().add("POST", api.MESSAGES_URL, resp)
    with pytest.raises(PollError) as info:
        api.probe_messages(transport, "tok")
    assert info.value.kind is kind
