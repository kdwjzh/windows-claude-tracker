"""確認假物件本身行為正確，且符合 core.interfaces 的 Protocol。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fakes import FakeClock, FakeCredentialSource, FakeProvider, FakeTransport
from usage_monitor.core.errors import ErrKind, PollError
from usage_monitor.core.interfaces import (
    Clock,
    CredentialSource,
    Provider,
    Response,
    Token,
    Transport,
)
from usage_monitor.core.models import Usage, Window

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
USAGE = Usage(Window(True, 42), Window(True, 18), NOW)

# 靜態檢查：pyright 會確認假物件符合 Protocol
_clock: Clock = FakeClock()
_transport: Transport = FakeTransport()
_provider: Provider = FakeProvider()
_source: CredentialSource = FakeCredentialSource()


def test_fake_clock_advances_only_when_told() -> None:
    clock = FakeClock(NOW)
    assert clock.now() == NOW
    clock.advance(30)
    clock.advance(minutes=1)
    assert (clock.now() - NOW).total_seconds() == 90


def test_fake_clock_rejects_naive_time() -> None:
    with pytest.raises(ValueError):
        FakeClock(datetime(2026, 1, 1))


def test_fake_transport_returns_queued_results_and_records_calls() -> None:
    url = "https://example.test/usage"
    transport = FakeTransport().add(
        "GET", url, Response(200, body=b"{}"), PollError(ErrKind.TRANSIENT, "逾時")
    )
    assert transport.get(url, {"a": "b"}, timeout=30).status == 200
    with pytest.raises(PollError):
        transport.get(url, {}, timeout=30)
    assert [c.method for c in transport.calls] == ["GET", "GET"]
    assert transport.calls[0].headers == {"a": "b"}


def test_fake_transport_post_records_json() -> None:
    url = "https://example.test/messages"
    transport = FakeTransport().add("POST", url, Response(200))
    transport.post(url, {}, json={"x": 1}, timeout=30)
    assert transport.calls[0].json == {"x": 1}


def test_fake_transport_unexpected_call_fails_loudly() -> None:
    with pytest.raises(AssertionError):
        FakeTransport().get("https://example.test/none", {}, timeout=30)


def test_fake_provider_sequence_then_repeats_last() -> None:
    err = PollError(ErrKind.AUTH, "未登入")
    provider = FakeProvider("claude", [err, USAGE])
    with pytest.raises(PollError):
        provider.poll()
    assert provider.poll() is USAGE
    assert provider.poll() is USAGE
    assert provider.poll_count == 3
    assert provider.display_name == "Claude"
    assert provider.credential_signature() == "sig-1"
    assert provider.source_label() == "假來源"


def test_fake_provider_without_results_fails_loudly() -> None:
    with pytest.raises(AssertionError):
        FakeProvider().poll()


def test_fake_credential_source() -> None:
    token = Token("t", expires_at=None, source="CLI")
    source = FakeCredentialSource("CLI", token)
    assert source.read() is token
    source.set_signature("sig-2")
    assert source.signature() == "sig-2"
    assert source.read_count == 1
