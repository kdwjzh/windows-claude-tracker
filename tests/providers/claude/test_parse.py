from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from usage_monitor.core.errors import ErrKind, PollError
from usage_monitor.core.interfaces import Response
from usage_monitor.providers.claude.parse import parse_headers, parse_usage

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)
FIXTURES = Path(__file__).parents[2] / "fixtures" / "claude"


def fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_legacy_fields() -> None:
    u = parse_usage(fixture("usage_legacy.json"), NOW)
    assert (u.session.available, u.session.percent, u.session.label) == (True, 42.0, "5h")
    assert u.session.resets_at == datetime(2026, 10, 29, 12, 13, 0, 123456, tzinfo=UTC)
    assert (u.long.available, u.long.percent, u.long.label) == (True, 18.5, "7d")
    assert u.long.resets_at == datetime(2026, 11, 2, 13, tzinfo=UTC)
    assert u.fetched_at == NOW


def test_limits_only_ignores_scoped_entries() -> None:
    u = parse_usage(fixture("usage_limits_only.json"), NOW)
    assert u.session.percent == 64  # 不是 weekly_scoped 的 77
    assert u.session.resets_at == datetime(2026, 10, 29, 12, 15, tzinfo=UTC)
    assert u.long.percent == 12.5  # 別名 utilization


def test_mixed_legacy_and_limits() -> None:
    u = parse_usage(
        {
            "five_hour": {"utilization": 42, "resets_at": "2026-10-24T07:00:00Z"},
            "seven_day": None,
            "limits": [{"kind": "weekly_all", "percent": 10, "scope": None}],
        },
        NOW,
    )
    assert (u.session.percent, u.long.percent) == (42, 10)
    assert u.long.resets_at is None


def test_zero_percent_is_available() -> None:
    u = parse_usage({"five_hour": {"utilization": 0}}, NOW)
    assert u.session.available and u.session.percent == 0
    assert not u.long.available
    assert u.long.label == "7d"


@pytest.mark.parametrize(
    "body",
    [
        fixture("usage_empty.json"),
        {},
        [],
        None,
        {"five_hour": {"utilization": None}, "limits": "nope"},
        {"five_hour": {"utilization": "abc"}},
        {"limits": [{"kind": "session", "scope": None}]},
        {"limits": [None, {"kind": "session", "scope": "opus", "percent": 5}]},
    ],
)
def test_no_windows_raises_transient(body: object) -> None:
    with pytest.raises(PollError) as info:
        parse_usage(body, NOW)
    assert info.value.kind is ErrKind.TRANSIENT


H = "anthropic-ratelimit-unified-"


def headers(**values: str) -> Response:
    return Response(200, {f"{H}{k.replace('_', '-')}": v for k, v in values.items()})


def test_headers_scale_fraction_to_percent() -> None:
    resp = headers(**{"5h_utilization": "0.5", "5h_reset": "1800000000", "7d_utilization": "0.07"})
    u = parse_headers(resp.header, NOW)
    assert u.session.percent == 50
    assert u.session.resets_at == datetime.fromtimestamp(1_800_000_000, tz=UTC)
    assert u.session.label == "5h"
    assert u.long.percent == pytest.approx(7)
    assert u.long.resets_at is None


def test_headers_are_case_insensitive() -> None:
    resp = Response(200, {"Anthropic-Ratelimit-Unified-5h-Utilization": "0.25"})
    assert parse_headers(resp.header, NOW).session.percent == 25


@pytest.mark.parametrize(
    ("claim", "session", "long"),
    [("five_hour", 100.0, 0.0), ("seven_day", 0.0, 100.0), ("other", 0.0, 0.0)],
)
def test_rejected_with_zero_utilization_uses_claim(claim: str, session: float, long: float) -> None:
    resp = headers(
        **{
            "5h_utilization": "0",
            "7d_utilization": "0",
            "status": "rejected",
            "representative_claim": claim,
        }
    )
    u = parse_headers(resp.header, NOW)
    assert (u.session.percent, u.long.percent) == (session, long)


def test_rejected_with_nonzero_utilization_keeps_values() -> None:
    resp = headers(
        **{
            "5h_utilization": "0.3",
            "7d_utilization": "0",
            "status": "rejected",
            "representative_claim": "seven_day",
        }
    )
    u = parse_headers(resp.header, NOW)
    assert (u.session.percent, u.long.percent) == (pytest.approx(30), 0)


def test_rejected_claim_marks_missing_window_available() -> None:
    resp = headers(**{"status": "rejected", "representative_claim": "five_hour"})
    u = parse_headers(resp.header, NOW)
    assert u.session.available and u.session.percent == 100


def test_allowed_status_not_forced() -> None:
    resp = headers(**{"5h_utilization": "0", "status": "allowed"})
    assert parse_headers(resp.header, NOW).session.percent == 0


def test_headers_without_windows_raise_transient() -> None:
    with pytest.raises(PollError) as info:
        parse_headers(headers(status="allowed").header, NOW)
    assert info.value.kind is ErrKind.TRANSIENT
