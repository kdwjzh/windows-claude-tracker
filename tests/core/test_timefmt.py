from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from usage_monitor.core import timefmt
from usage_monitor.core.i18n import Lang

NOW = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)  # 台北 18:00（週四）
TPE = timezone(timedelta(hours=8))


@pytest.mark.parametrize(
    ("delta", "text"),
    [
        (timedelta(hours=2, minutes=13), "2時13分"),
        (timedelta(hours=2, minutes=5), "2時05分"),
        (timedelta(minutes=48, seconds=59), "48分"),
        (timedelta(days=4, hours=3, minutes=59), "4天3時"),
        (timedelta(days=1, hours=2), "1天2時"),
        (timedelta(days=9, hours=23), "9天23時"),
        (timedelta(days=10, hours=5), "10天"),
        (timedelta(days=29, hours=1), "29天"),
        (timedelta(seconds=59), "即將重置"),
        (timedelta(0), "即將重置"),
        (timedelta(minutes=-5), "即將重置"),
    ],
)
def test_countdown(delta: timedelta, text: str) -> None:
    assert timefmt.countdown(NOW + delta, NOW) == text


def test_clock_converts_to_local() -> None:
    assert timefmt.clock(datetime(2026, 10, 29, 12, 15, tzinfo=UTC), TPE) == "20:15"


@pytest.mark.parametrize(
    ("resets_at", "text"),
    [
        (datetime(2026, 10, 29, 12, 20, tzinfo=UTC), "今天 20:20"),
        (datetime(2026, 10, 30, 0, 0, tzinfo=UTC), "明天 08:00"),
        (datetime(2026, 11, 1, 14, 0, tzinfo=UTC), "11/01（日）22:00"),
        (datetime(2026, 10, 31, 14, 0, tzinfo=UTC), "10/31（六）22:00"),
    ],
)
def test_reset_moment(resets_at: datetime, text: str) -> None:
    assert timefmt.reset_moment(resets_at, NOW, TPE) == text


def test_reset_moment_today_depends_on_local_date() -> None:
    # UTC 已經是 10/30，但台北仍是 10/29 晚上 → 不是「明天」
    now = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)  # 台北 23:00
    assert timefmt.reset_moment(datetime(2026, 10, 29, 15, 30, tzinfo=UTC), now, TPE) == (
        "今天 23:30"
    )


@pytest.mark.parametrize(
    ("delta", "text"),
    [
        (timedelta(hours=2, minutes=13), "2h 13m"),
        (timedelta(hours=2, minutes=5), "2h 5m"),
        (timedelta(minutes=48), "48m"),
        (timedelta(days=4, hours=3), "4d 3h"),
        (timedelta(days=29, hours=1), "29d"),
        (timedelta(seconds=30), "soon"),
    ],
)
def test_countdown_english(delta: timedelta, text: str) -> None:
    assert timefmt.countdown(NOW + delta, NOW, Lang.EN) == text


@pytest.mark.parametrize(
    ("resets_at", "text"),
    [
        (datetime(2026, 10, 29, 12, 20, tzinfo=UTC), "today 20:20"),
        (datetime(2026, 10, 30, 0, 0, tzinfo=UTC), "tomorrow 08:00"),
        (datetime(2026, 11, 1, 14, 0, tzinfo=UTC), "Sun 11/01 22:00"),
    ],
)
def test_reset_moment_english(resets_at: datetime, text: str) -> None:
    assert timefmt.reset_moment(resets_at, NOW, TPE, Lang.EN) == text


@pytest.mark.parametrize(
    ("delta", "text"),
    [
        (timedelta(seconds=30), "just now"),
        (timedelta(minutes=12), "12 min ago"),
        (timedelta(hours=3), "3 hr ago"),
        (timedelta(days=1, hours=1), "1 day ago"),
        (timedelta(days=2), "2 days ago"),
    ],
)
def test_ago_english(delta: timedelta, text: str) -> None:
    assert timefmt.ago(NOW - delta, NOW, Lang.EN) == text


@pytest.mark.parametrize(
    ("delta", "text"),
    [
        (timedelta(seconds=30), "剛剛"),
        (timedelta(minutes=12), "12 分鐘前"),
        (timedelta(hours=3, minutes=5), "3 小時前"),
        (timedelta(days=2, hours=1), "2 天前"),
    ],
)
def test_ago(delta: timedelta, text: str) -> None:
    assert timefmt.ago(NOW - delta, NOW) == text
