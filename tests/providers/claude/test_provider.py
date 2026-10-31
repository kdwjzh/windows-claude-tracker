from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fakes import FakeClock, FakeCredentialSource, FakeTransport
from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.interfaces import Response, Token
from usage_monitor.providers.claude import api
from usage_monitor.providers.claude.credentials.cli import CliCredentialSource
from usage_monitor.providers.claude.credentials.desktop import DesktopCredentialSource
from usage_monitor.providers.claude.provider import ClaudeProvider, create

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)
FIXTURES = Path(__file__).parents[2] / "fixtures" / "claude"
LEGACY = (FIXTURES / "usage_legacy.json").read_bytes()


def token(value: str, source: str, *, expired: bool = False) -> Token:
    delta = timedelta(minutes=-1 if expired else 60)
    return Token(value, expires_at=NOW + delta, source=source)


def provider(transport: FakeTransport, *sources: FakeCredentialSource) -> ClaudeProvider:
    return ClaudeProvider(list(sources), transport, FakeClock(NOW))


def test_poll_usage_endpoint() -> None:
    transport = FakeTransport().add("GET", api.USAGE_URL, Response(200, body=LEGACY))
    p = provider(transport, FakeCredentialSource("桌面版", token("desk", "桌面版")))
    usage = p.poll()
    assert (usage.session.percent, usage.long.percent) == (42.0, 18.5)
    assert usage.fetched_at == NOW
    assert p.source_label() == "桌面版"
    assert transport.calls[0].headers["Authorization"] == "Bearer desk"


def test_cli_preferred_when_valid() -> None:
    transport = FakeTransport().add("GET", api.USAGE_URL, Response(200, body=LEGACY))
    cli = FakeCredentialSource("CLI", token("cli", "CLI"))
    desk = FakeCredentialSource("桌面版", token("desk", "桌面版"))
    provider(transport, cli, desk).poll()
    assert transport.calls[0].headers["Authorization"] == "Bearer cli"
    assert desk.read_count == 0


def test_expired_cli_falls_through_to_desktop() -> None:
    transport = FakeTransport().add("GET", api.USAGE_URL, Response(200, body=LEGACY))
    cli = FakeCredentialSource("CLI", token("cli", "CLI", expired=True))
    desk = FakeCredentialSource("桌面版", token("desk", "桌面版"))
    p = provider(transport, cli, desk)
    p.poll()
    assert transport.calls[0].headers["Authorization"] == "Bearer desk"
    assert p.source_label() == "桌面版"


def test_no_token_is_auth_error_without_calling_api() -> None:
    transport = FakeTransport()
    p = provider(transport, FakeCredentialSource("CLI"), FakeCredentialSource("桌面版"))
    with pytest.raises(PollError) as info:
        p.poll()
    assert info.value.kind is ErrKind.AUTH
    assert "找不到" in info.value.message
    assert transport.calls == []
    assert p.source_label() is None


def test_only_expired_tokens_is_auth_error() -> None:
    transport = FakeTransport()
    p = provider(transport, FakeCredentialSource("CLI", token("cli", "CLI", expired=True)))
    with pytest.raises(PollError) as info:
        p.poll()
    assert info.value.kind is ErrKind.AUTH
    assert "過期" in info.value.message
    assert "cli" not in info.value.message.replace("CLI", "")
    assert p.source_label() == "CLI"
    assert transport.calls == []


def test_source_exception_is_skipped() -> None:
    class Broken(FakeCredentialSource):
        def read(self) -> Token | None:
            raise RuntimeError("boom")

    transport = FakeTransport().add("GET", api.USAGE_URL, Response(200, body=LEGACY))
    p = provider(transport, Broken("CLI"), FakeCredentialSource("桌面版", token("d", "桌面版")))
    assert p.poll().session.percent == 42.0


@pytest.mark.parametrize(("status", "kind"), [(401, ErrKind.AUTH), (429, ErrKind.TRANSIENT)])
def test_auth_and_transient_do_not_fall_back(status: int, kind: ErrKind) -> None:
    transport = FakeTransport().add("GET", api.USAGE_URL, Response(status))
    p = provider(transport, FakeCredentialSource("桌面版", token("d", "桌面版")))
    with pytest.raises(PollError) as info:
        p.poll()
    assert info.value.kind is kind
    assert [c.method for c in transport.calls] == ["GET"]


def test_unsupported_falls_back_to_messages_headers() -> None:
    headers = {
        "anthropic-ratelimit-unified-5h-utilization": "0.42",
        "anthropic-ratelimit-unified-7d-utilization": "0.18",
    }
    transport = (
        FakeTransport()
        .add("GET", api.USAGE_URL, Response(404))
        .add("POST", api.MESSAGES_URL, Response(200, headers))
    )
    p = provider(transport, FakeCredentialSource("桌面版", token("d", "桌面版")))
    usage = p.poll()
    assert usage.session.percent == pytest.approx(42)
    assert usage.long.percent == pytest.approx(18)
    assert [c.method for c in transport.calls] == ["GET", "POST"]


def test_invalid_json_is_transient() -> None:
    transport = FakeTransport().add("GET", api.USAGE_URL, Response(200, body=b"<html>"))
    p = provider(transport, FakeCredentialSource("桌面版", token("d", "桌面版")))
    with pytest.raises(PollError) as info:
        p.poll()
    assert info.value.kind is ErrKind.TRANSIENT


def test_network_error_propagates() -> None:
    transport = FakeTransport().add("GET", api.USAGE_URL, PollError(ErrKind.TRANSIENT, "連線逾時"))
    p = provider(transport, FakeCredentialSource("桌面版", token("d", "桌面版")))
    with pytest.raises(PollError, match="連線逾時"):
        p.poll()


def test_credential_signature_combines_sources() -> None:
    cli = FakeCredentialSource("CLI", signature="a")
    desk = FakeCredentialSource("桌面版", signature="b")
    p = provider(FakeTransport(), cli, desk)
    first = p.credential_signature()
    desk.set_signature("c")
    assert p.credential_signature() != first


def test_identity() -> None:
    p = provider(FakeTransport())
    assert (p.id, p.display_name) == ("claude", "Claude")


# ---------------------------------------------------------------- 階段 7：CLI token 更新


class RefreshingCli(FakeCredentialSource):
    """模擬 claude 執行後 .credentials.json 被寫入新 token。"""

    def __init__(self) -> None:
        super().__init__("cli", token("old", "cli", expired=True))
        self.refresh_calls = 0

    def refresh(self) -> bool:
        self.refresh_calls += 1
        self.token = token("new", "cli")
        return True


def test_cli_refresh_used_when_nothing_else_works() -> None:
    transport = FakeTransport().add("GET", api.USAGE_URL, Response(200, body=LEGACY))
    cli = RefreshingCli()
    p = provider(transport, cli, FakeCredentialSource("desktop"))
    p.configure_cli_refresh(cli.refresh, lambda: True)
    p.poll()
    assert cli.refresh_calls == 1
    assert transport.calls[0].headers["Authorization"] == "Bearer new"
    assert p.source_label() == "cli"


def test_cli_refresh_disabled_by_setting() -> None:
    cli = RefreshingCli()
    p = provider(FakeTransport(), cli)
    p.configure_cli_refresh(cli.refresh, lambda: False)
    with pytest.raises(PollError) as info:
        p.poll()
    assert info.value.kind is ErrKind.AUTH
    assert cli.refresh_calls == 0


def test_cli_refresh_skipped_when_desktop_token_is_valid() -> None:
    """有桌面版可用時不更新 CLI，避免白白花額度。"""
    transport = FakeTransport().add("GET", api.USAGE_URL, Response(200, body=LEGACY))
    cli = RefreshingCli()
    p = provider(transport, cli, FakeCredentialSource("desktop", token("desk", "desktop")))
    p.configure_cli_refresh(cli.refresh, lambda: True)
    p.poll()
    assert cli.refresh_calls == 0
    assert transport.calls[0].headers["Authorization"] == "Bearer desk"


def test_cli_refresh_only_for_cli_source() -> None:
    called: list[int] = []
    p = provider(
        FakeTransport(), FakeCredentialSource("desktop", token("d", "desktop", expired=True))
    )
    p.configure_cli_refresh(lambda: bool(called.append(1)), lambda: True)
    with pytest.raises(PollError):
        p.poll()
    assert called == []


@pytest.mark.parametrize("outcome", ["fails", "still_expired", "raises"])
def test_cli_refresh_unsuccessful_is_auth_error(outcome: str) -> None:
    cli = FakeCredentialSource("cli", token("old", "cli", expired=True))

    def refresh() -> bool:
        if outcome == "raises":
            raise RuntimeError("boom")
        return outcome == "still_expired"

    p = provider(FakeTransport(), cli)
    p.configure_cli_refresh(refresh, lambda: True)
    with pytest.raises(PollError) as info:
        p.poll()
    assert info.value.reason is ErrReason.EXPIRED


def test_create_uses_cli_then_desktop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    (tmp_path / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"accessToken": "from-cli"}}), encoding="utf-8"
    )
    p = create(FakeTransport(), FakeClock(NOW))
    assert isinstance(p, ClaudeProvider)
    sources = p._sources  # pyright: ignore[reportPrivateUsage]
    assert [type(s) for s in sources] == [CliCredentialSource, DesktopCredentialSource]
    tok = sources[0].read()
    assert tok is not None and tok.value == "from-cli"
