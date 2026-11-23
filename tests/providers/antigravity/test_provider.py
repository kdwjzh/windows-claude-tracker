from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fakes import FakeClock, FakeTransport
from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.interfaces import Response
from usage_monitor.providers import registry
from usage_monitor.providers.antigravity.hub import Hub, HubSource
from usage_monitor.providers.antigravity.provider import AntigravityProvider, create

NOW = datetime(2026, 11, 23, 7, tzinfo=UTC)
FIXTURES = Path(__file__).parents[2] / "fixtures" / "antigravity"
SUMMARY = (FIXTURES / "quota_summary_weekly.json").read_bytes()
STATUS = json.dumps(
    {"userStatus": {"email": "a@example.com", "userTier": {"id": "g1-plus-tier"}}}
).encode()
BASE = "http://127.0.0.1:56767/exa.language_server_pb.LanguageServerService/"
HUB = Hub(5000, 56767, "csrf-1")


class StubSource(HubSource):
    def __init__(self, hub: Hub | None) -> None:
        super().__init__(Path("unused"))
        self.hub = hub

    def read(self) -> Hub | None:
        return self.hub


def make(transport: FakeTransport, hub: Hub | None = HUB) -> AntigravityProvider:
    return AntigravityProvider(StubSource(hub), transport, FakeClock(NOW))


def test_poll_reads_quota_and_plan_from_local_server() -> None:
    transport = (
        FakeTransport()
        .add("POST", BASE + "RetrieveUserQuotaSummary", Response(200, body=SUMMARY))
        .add("POST", BASE + "GetUserStatus", Response(200, body=STATUS))
    )
    p = make(transport)
    usage = p.poll()
    assert ([w.label for w in usage.scoped], usage.plan) == (["Gem", "C/G"], "Plus")
    call = transport.calls[0]
    assert call.headers == {"Content-Type": "application/json", "X-Codeium-Csrf-Token": "csrf-1"}
    assert (call.json, call.timeout) == ({}, 30)
    assert p.source_label() == "antigravity"


def test_plan_failure_does_not_fail_poll() -> None:
    transport = (
        FakeTransport()
        .add("POST", BASE + "RetrieveUserQuotaSummary", Response(200, body=SUMMARY))
        .add("POST", BASE + "GetUserStatus", Response(500))
    )
    assert make(transport).poll().plan is None


def test_not_running_pauses_quietly() -> None:
    p = make(FakeTransport(), hub=None)
    with pytest.raises(PollError) as e:
        p.poll()
    assert (e.value.kind, e.value.reason) == (ErrKind.AUTH, ErrReason.NOT_RUNNING)
    assert p.source_label() is None


@pytest.mark.parametrize(
    ("status", "kind", "reason"),
    [
        (401, ErrKind.AUTH, ErrReason.REJECTED),
        (500, ErrKind.TRANSIENT, ErrReason.SERVER),
        (404, ErrKind.TRANSIENT, ErrReason.BAD_RESPONSE),
    ],
)
def test_http_errors(status: int, kind: ErrKind, reason: ErrReason) -> None:
    transport = FakeTransport().add("POST", BASE + "RetrieveUserQuotaSummary", Response(status))
    with pytest.raises(PollError) as e:
        make(transport).poll()
    assert (e.value.kind, e.value.reason, e.value.status) == (kind, reason, status)


def test_non_json_is_bad_response() -> None:
    transport = FakeTransport().add(
        "POST", BASE + "RetrieveUserQuotaSummary", Response(200, body=b"<")
    )
    with pytest.raises(PollError) as e:
        make(transport).poll()
    assert e.value.reason is ErrReason.BAD_RESPONSE


def test_registered_and_signature_from_hub_dir(tmp_path: Path) -> None:
    assert "antigravity" in registry.available()
    p = create(FakeTransport(), FakeClock(NOW))
    assert (p.id, p.display_name) == ("antigravity", "Antigravity")
    source = HubSource(tmp_path)
    q = AntigravityProvider(source, FakeTransport(), FakeClock(NOW))
    before = q.credential_signature()
    (tmp_path / "hub_1.json").write_text("{}", encoding="utf-8")
    assert q.credential_signature() not in (before, "")
