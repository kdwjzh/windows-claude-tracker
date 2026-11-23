from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from usage_monitor.core.errors import ErrReason, PollError
from usage_monitor.core.models import Window
from usage_monitor.providers.antigravity.parse import parse_plan, parse_usage

NOW = datetime(2026, 11, 23, 7, tzinfo=UTC)
FIXTURES = Path(__file__).parents[2] / "fixtures" / "antigravity"
# GetUserStatus 只取需要的部分（完整回應有帳號資料，不存成 fixture）
STATUS = {
    "userStatus": {
        "name": "someone",
        "email": "someone@example.com",
        "planStatus": {"planInfo": {"planName": "Pro", "teamsTier": "TEAMS_TIER_PRO"}},
        "userTier": {"id": "g1-plus-tier", "name": "Antigravity Starter Quota"},
    }
}


def load(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def at(text: str) -> datetime:
    return datetime.fromisoformat(text)


def test_weekly_only_groups_become_scoped_rows_named_by_group() -> None:
    """免費／Plus（Starter）只有週限制：標籤是分組短名，短週期沒回報、長週期取最高的分組。"""
    usage = parse_usage(load("quota_summary_weekly.json"), NOW)
    assert usage.session == Window(label="5h")
    assert (round(usage.long.percent, 2), usage.long.resets_at) == (
        10.79,
        at("2026-11-30T06:01:23Z"),
    )
    assert [(w.label, round(w.percent, 2)) for w in usage.scoped] == [("Gem", 10.79), ("C/G", 0.0)]
    assert usage.scoped[1].resets_at == at("2026-11-30T06:31:17Z")


def test_paid_plan_takes_highest_of_each_window_and_labels_period() -> None:
    usage = parse_usage(load("quota_summary_5h.json"), NOW)
    assert (round(usage.session.percent), usage.session.resets_at) == (
        31,
        at("2026-11-23T09:00:00Z"),
    )
    # argon 桶沒有 remainingFraction、重置時間還沒到：proto3 省略零值 → 已用完
    assert (usage.long.percent, usage.long.label) == (100, "7d")
    assert [(w.label, round(w.percent)) for w in usage.scoped] == [
        ("Gem 5h", 31), ("Gem 7d", 12), ("Argon 7d", 100), ("C/G 5h", 5), ("C/G 7d", 40),
    ]  # fmt: skip


def test_missing_fraction_with_past_reset_is_skipped() -> None:
    body = {"response": {"groups": [{"displayName": "Gemini Models", "buckets": [
        {"bucketId": "gemini-weekly", "window": "weekly", "resetTime": "2026-11-01T00:00:00Z"},
        {"bucketId": "gemini-5h", "window": "5h", "remainingFraction": 0.5},
        {"bucketId": "gemini-x", "window": "monthly", "remainingFraction": 0.5},
        "not a bucket",
    ]}]}}  # fmt: skip
    usage = parse_usage(body, NOW)
    assert [w.label for w in usage.scoped] == ["Gem 5h"]
    assert usage.long == Window(label="7d")


@pytest.mark.parametrize("body", [None, [], {}, {"response": {"groups": []}}, {"groups": [{}]}])
def test_no_quota_is_bad_response(body: object) -> None:
    with pytest.raises(PollError) as e:
        parse_usage(body, NOW)
    assert e.value.reason is ErrReason.BAD_RESPONSE


def test_unknown_group_uses_first_word_of_its_name() -> None:
    body = {"groups": [{"displayName": "Image models", "buckets": [
        {"window": "weekly", "remainingFraction": 0.25, "resetTime": "2026-11-30T00:00:00Z"}
    ]}]}  # fmt: skip
    assert parse_usage(body, NOW).scoped[0].label == "Image"


def test_plan_comes_only_from_user_tier_id() -> None:
    assert parse_plan(STATUS) == "Plus"
    tier = {"userStatus": {"userTier": {"id": "g1-ultra-lite-tier"}}}
    assert parse_plan(tier) == "Ultra Lite"


@pytest.mark.parametrize(
    "body",
    [None, {}, {"userStatus": {"planStatus": {"planInfo": {"planName": "Pro"}}}},
     {"userStatus": {"userTier": {"id": "free"}}}],
)  # fmt: skip
def test_plan_unknown_is_none(body: object) -> None:
    assert parse_plan(body) is None
