from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from usage_monitor.core.errors import ErrKind, PollError
from usage_monitor.core.interfaces import Response
from usage_monitor.providers.claude.parse import parse_headers, parse_plan, parse_usage

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


# ---------------------------------------------------------------- API 格式變動（ROADMAP 第 14 項）


def test_full_2026_11_response(caplog: pytest.LogCaptureFixture) -> None:
    """2026-11 的實際回應（diagnose --dump-response 存下、已去識別化）：解析正確、沒有雜訊 log。"""
    caplog.set_level("DEBUG", logger="usage_monitor.providers.claude.parse")
    u = parse_usage(fixture("usage_full_2026_11.json"), NOW)
    assert (u.session.percent, u.session.label) == (57.0, "5h")
    assert (u.long.percent, u.long.label) == (65.0, "7d")
    assert "不認得" not in caplog.text  # 一堆值是 null 的代號欄位不算


def test_unknown_fields_and_kinds_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("DEBUG", logger="usage_monitor.providers.claude.parse")
    body = fixture("usage_full_2026_11.json")
    assert isinstance(body, dict)
    body["new_window"] = {"utilization": 3}
    body["another_codename"] = None  # null 不記
    body["five_hour"]["burst"] = 1
    body["limits"].append({"kind": "daily_all", "scope": None, "percent": 5, "colour": "red"})
    u = parse_usage(body, NOW)
    assert u.session.percent == 57.0  # 照常解析
    assert "不認得的欄位：five_hour.burst, limits[].colour, new_window" in caplog.text
    assert "不認得的 kind：daily_all" in caplog.text
    assert "another_codename" not in caplog.text
    assert "utilization" not in caplog.text.split("不認得的欄位：")[1].split("\n")[0]


# ------------------------------------------------------ 模型專屬的每週限制（weekly_scoped）


def test_scoped_2026_11_response(caplog: pytest.LogCaptureFixture) -> None:
    """2026-11-13 的實際回應：多了 Fable 的 weekly_scoped（名稱被去識別化成 <redacted>）。"""
    caplog.set_level("DEBUG", logger="usage_monitor.providers.claude.parse")
    u = parse_usage(fixture("usage_scoped_2026_11.json"), NOW)
    assert (u.session.percent, u.long.percent) == (86.0, 74.0)
    assert len(u.scoped) == 1
    w = u.scoped[0]
    assert (w.available, w.percent, w.label, w.share) == (True, 94.0, "<redacted>", 50.0)
    assert w.resets_at == datetime(2026, 11, 13, 12, 0, 0, 362260, tzinfo=UTC)
    assert "不認得" not in caplog.text


def scoped(name: object, percent: object = 10, **extra: object) -> dict[str, object]:
    return {
        "kind": "weekly_scoped",
        "percent": percent,
        "resets_at": "2026-11-13T12:00:00Z",
        "scope": {"model": {"id": None, "display_name": name}, "surface": None},
        **extra,
    }


def test_every_scoped_model_is_listed_in_order() -> None:
    """之後出現的新模型不用改程式就會顯示；分享比例依 limit_index 對到 limits[] 的位置。"""
    body = {
        "limits": [
            {"kind": "session", "scope": None, "percent": 5},
            scoped("Fable", 94),
            scoped("Opus", utilization=30.5, percent=None),
        ],
        "weekly_scoped_shares": [
            {"limit_index": 2, "allowance_percent_of_weekly": 40},
            {"limit_index": "1", "allowance_percent_of_weekly": 50},  # 不是整數：忽略
            None,
        ],
    }
    u = parse_usage(body, NOW)
    assert [(w.label, w.percent, w.share) for w in u.scoped] == [
        ("Fable", 94.0, None),
        ("Opus", 30.5, 40.0),
    ]
    assert u.session.percent == 5


@pytest.mark.parametrize(
    "item",
    [
        scoped(None),
        scoped(""),
        scoped("Fable", percent=None),
        {"kind": "weekly_scoped", "scope": "opus", "percent": 77},  # 舊的猜測格式
        {"kind": "weekly_scoped", "scope": {"model": None}, "percent": 77},
        "nope",
    ],
)
def test_malformed_scoped_items_are_skipped(item: object) -> None:
    u = parse_usage({"limits": [{"kind": "session", "scope": None, "percent": 5}, item]}, NOW)
    assert u.scoped == ()


def test_no_scoped_limits_means_empty_tuple() -> None:
    assert parse_usage(fixture("usage_full_2026_11.json"), NOW).scoped == ()
    assert parse_usage(fixture("usage_legacy.json"), NOW).scoped == ()


@pytest.mark.parametrize(
    ("org", "plan"),
    [
        ({"organization_type": "claude_pro", "rate_limit_tier": "default_claude_ai"}, "Pro"),
        ({"organization_type": "claude_max", "rate_limit_tier": "default_claude_max_5x"}, "Max 5x"),
        (
            {"organization_type": "claude_max", "rate_limit_tier": "default_claude_max_20x"},
            "Max 20x",
        ),
        ({"organization_type": "claude_max", "rate_limit_tier": None}, "Max"),
        ({"organization_type": "claude_team"}, "Team"),
        ({"organization_type": "claude_enterprise"}, "Enterprise"),
        ({"organization_type": "claude_new_plan"}, "New plan"),  # 不認得：照名稱顯示
        ({"organization_type": None}, None),
        ({}, None),
    ],
)
def test_parse_plan(org: dict[str, object], plan: str | None) -> None:
    body = {"account": {"email": "a@b.c", "has_claude_pro": True}, "organization": org}
    assert parse_plan(body) == plan


@pytest.mark.parametrize("body", [None, [], {"organization": "x"}])
def test_parse_plan_tolerates_garbage(body: object) -> None:
    assert parse_plan(body) is None
