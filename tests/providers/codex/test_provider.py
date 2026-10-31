from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fakes import FakeClock, FakeTransport
from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.interfaces import Response
from usage_monitor.providers import registry
from usage_monitor.providers.codex import api
from usage_monitor.providers.codex.credentials import CodexCredentialSource
from usage_monitor.providers.codex.provider import CodexProvider, create

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)
FIXTURES = Path(__file__).parents[2] / "fixtures" / "codex"
WEEK = (FIXTURES / "usage_week.json").read_bytes()


def jwt(exp: datetime) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": int(exp.timestamp())}).encode())
    return f"e30.{payload.decode().rstrip('=')}.c2ln"


def provider(
    tmp_path: Path,
    transport: FakeTransport,
    *,
    token: str | None = None,
    account_id: str | None = "acct-1",
) -> CodexProvider:
    path = tmp_path / "auth.json"
    if token is not None:
        path.write_text(
            json.dumps({"tokens": {"access_token": token, "account_id": account_id}}),
            encoding="utf-8",
        )
    return CodexProvider(CodexCredentialSource(path), transport, FakeClock(NOW))


def test_poll_sends_expected_headers(tmp_path: Path) -> None:
    transport = FakeTransport().add("GET", api.USAGE_URL, Response(200, body=WEEK))
    token = jwt(NOW + timedelta(days=3))
    p = provider(tmp_path, transport, token=token)
    usage = p.poll()
    assert (usage.session.percent, usage.long.label) == (12, "7d")
    assert transport.calls[0].headers == {
        "Authorization": f"Bearer {token}",
        "User-Agent": "codex-cli",
        "ChatGPT-Account-Id": "acct-1",
    }
    assert transport.calls[0].timeout == 30
    assert p.source_label() == "codex_cli"


def test_account_header_only_when_present(tmp_path: Path) -> None:
    transport = FakeTransport().add("GET", api.USAGE_URL, Response(200, body=WEEK))
    provider(tmp_path, transport, token="opaque", account_id=None).poll()
    assert "ChatGPT-Account-Id" not in transport.calls[0].headers


def test_not_installed_is_auth_error_without_api_call(tmp_path: Path) -> None:
    transport = FakeTransport()
    p = provider(tmp_path, transport)
    with pytest.raises(PollError) as info:
        p.poll()
    assert info.value.kind is ErrKind.AUTH
    assert transport.calls == []
    assert p.source_label() is None


def test_expired_jwt_is_auth_error_without_api_call(tmp_path: Path) -> None:
    transport = FakeTransport()
    p = provider(tmp_path, transport, token=jwt(NOW - timedelta(minutes=1)))
    with pytest.raises(PollError, match="過期") as info:
        p.poll()
    assert info.value.kind is ErrKind.AUTH
    assert transport.calls == []


@pytest.mark.parametrize(
    ("resp", "kind"),
    [
        (Response(401), ErrKind.AUTH),
        (Response(403), ErrKind.AUTH),
        (Response(429, {"Retry-After": "120"}), ErrKind.TRANSIENT),
        (Response(502), ErrKind.TRANSIENT),
        (Response(404), ErrKind.UNSUPPORTED),
        (Response(301), ErrKind.TRANSIENT),
        (Response(200, body=b"<html>"), ErrKind.TRANSIENT),
    ],
)
def test_error_classification(tmp_path: Path, resp: Response, kind: ErrKind) -> None:
    transport = FakeTransport().add("GET", api.USAGE_URL, resp)
    with pytest.raises(PollError) as info:
        provider(tmp_path, transport, token="opaque").poll()
    assert info.value.kind is kind


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (403, ErrReason.REJECTED),
        (429, ErrReason.RATE_LIMITED),
        (500, ErrReason.SERVER),
        (400, ErrReason.UNSUPPORTED),
        (304, ErrReason.BAD_RESPONSE),
    ],
)
def test_status_reason(status: int, reason: ErrReason) -> None:
    with pytest.raises(PollError) as info:
        api.raise_for_status(Response(status))
    assert info.value.reason is reason


def test_auth_reasons(tmp_path: Path) -> None:
    with pytest.raises(PollError) as missing:
        provider(tmp_path, FakeTransport()).poll()
    assert missing.value.reason is ErrReason.NO_CREDENTIALS
    with pytest.raises(PollError) as expired:
        provider(tmp_path, FakeTransport(), token=jwt(NOW - timedelta(minutes=1))).poll()
    assert expired.value.reason is ErrReason.EXPIRED


def test_retry_after_parsing() -> None:
    assert api.retry_after(Response(429, {"retry-after": "120"})) == 120
    assert api.retry_after(Response(429, {"retry-after": "-5"})) is None
    assert api.retry_after(Response(429, {"retry-after": "later"})) is None


def test_signature_and_identity(tmp_path: Path) -> None:
    p = provider(tmp_path, FakeTransport(), token="opaque")
    signature = p.credential_signature()
    assert signature.startswith(str(tmp_path / "auth.json") + "|")
    assert "opaque" not in signature
    assert (p.id, p.display_name) == ("codex", "Codex")


def test_registered_with_one_line() -> None:
    assert registry.available() == ["claude", "codex"]
    assert isinstance(create(FakeTransport(), FakeClock(NOW)), CodexProvider)
    assert registry.create("codex", FakeTransport(), FakeClock(NOW)).id == "codex"
