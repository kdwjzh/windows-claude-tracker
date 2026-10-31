from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from usage_monitor.core.errors import ErrKind, PollError
from usage_monitor.providers.codex.parse import parse_usage

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)
FIXTURES = Path(__file__).parents[2] / "fixtures" / "codex"


def fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_five_hour_and_week() -> None:
    u = parse_usage(fixture("usage_week.json"), NOW)
    assert (u.session.percent, u.session.label) == (12, "5h")
    assert u.session.resets_at == datetime.fromtimestamp(1_793_280_000, tz=UTC)
    assert (u.long.percent, u.long.label) == (6.5, "7d")
    assert u.fetched_at == NOW


def test_month_window_classified_by_length_not_order() -> None:
    """primary 是 30 天、secondary 是 5 小時：依 limit_window_seconds 分類，標籤是 30d。"""
    u = parse_usage(fixture("usage_month_reversed.json"), NOW)
    assert (u.session.percent, u.session.label) == (35, "5h")
    assert (u.long.percent, u.long.label) == (6, "30d")
    # 沒有 reset_at 時用 reset_after_seconds
    assert u.session.resets_at == NOW + timedelta(seconds=7500)
    assert u.long.resets_at == NOW + timedelta(days=29)


@pytest.mark.parametrize(
    ("seconds", "label"),
    [(18_000, "5h"), (604_800, "7d"), (2_592_000, "30d"), (2_505_600, "29d"), (86_400, "1d")],
)
def test_label_follows_window_length(seconds: int, label: str) -> None:
    body = {
        "rate_limit": {"secondary_window": {"used_percent": 1, "limit_window_seconds": seconds}}
    }
    u = parse_usage(body, NOW)
    window = u.long if seconds >= 86_400 else u.session
    assert window.label == label


def test_missing_window_length_falls_back_to_position() -> None:
    body = {
        "rate_limit": {
            "primary_window": {"used_percent": 20},
            "secondary_window": {"used_percent": 3},
        }
    }
    u = parse_usage(body, NOW)
    assert (u.session.percent, u.session.label) == (20, "5h")
    assert (u.long.percent, u.long.label) == (3, "7d")


def test_two_long_windows_do_not_overwrite() -> None:
    body = {
        "rate_limit": {
            "primary_window": {"used_percent": 1, "limit_window_seconds": 604_800},
            "secondary_window": {"used_percent": 2, "limit_window_seconds": 2_592_000},
        }
    }
    u = parse_usage(body, NOW)
    assert (u.long.percent, u.long.label) == (1, "7d")
    assert (u.session.percent, u.session.label) == (2, "30d")


def test_two_short_windows_do_not_overwrite() -> None:
    body = {
        "rate_limit": {
            "primary_window": {"used_percent": 1, "limit_window_seconds": 18_000},
            "secondary_window": {"used_percent": 2, "limit_window_seconds": 3_600},
        }
    }
    u = parse_usage(body, NOW)
    assert (u.session.percent, u.long.percent) == (1, 2)
    assert u.long.label == "1h"


def test_only_one_window() -> None:
    body = {"rate_limit": {"primary_window": {"used_percent": 0, "limit_window_seconds": 18_000}}}
    u = parse_usage(body, NOW)
    assert u.session.available and u.session.percent == 0
    assert not u.long.available
    assert u.long.label == "7d"


@pytest.mark.parametrize(
    "body",
    [
        fixture("usage_no_windows.json"),
        {},
        None,
        [],
        {"rate_limit": "x"},
        {"rate_limit": {"primary_window": {"used_percent": "abc"}}},
        {"rate_limit": {"primary_window": {"limit_window_seconds": 18000}}},
    ],
)
def test_no_windows_is_transient(body: object) -> None:
    with pytest.raises(PollError) as info:
        parse_usage(body, NOW)
    assert info.value.kind is ErrKind.TRANSIENT


def test_negative_reset_after_ignored() -> None:
    body = {"rate_limit": {"primary_window": {"used_percent": 5, "reset_after_seconds": -1}}}
    assert parse_usage(body, NOW).session.resets_at is None
