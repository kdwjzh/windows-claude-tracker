"""儀表板「用量」頁的 ViewModel（ROADMAP 第 5b 項）：歷史紀錄 → 折線、長條、平均。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from usage_monitor.core.i18n import Lang
from usage_monitor.core.levels import Level
from usage_monitor.core.models import ProviderState, Usage, Window
from usage_monitor.services.history import Sample
from usage_monitor.ui.usage_vm import (
    MAX_CYCLES,
    BarVM,
    average_text,
    build_service_usage,
    cycle_bars,
    line_vm,
)

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)  # 台北 20:00


def session(at: datetime, percent: float) -> Sample:
    return Sample("claude", "session", "5h", at, percent, at + timedelta(hours=1))


def long(at: datetime, percent: float, resets_at: datetime, label: str = "7d") -> Sample:
    return Sample("claude", "long", label, at, percent, resets_at)


def test_line_keeps_last_7_days_and_breaks_on_gaps() -> None:
    old = session(NOW - timedelta(days=8), 50)
    a = session(NOW - timedelta(hours=5), 10)
    b = session(NOW - timedelta(hours=4, minutes=55), 12)
    c = session(NOW - timedelta(hours=1), 40)  # 相隔約 4 小時（程式沒開）→ 新的一段
    vm = line_vm([old, a, b, long(NOW, 99, NOW), c], NOW, TPE)
    assert vm.start == NOW - timedelta(days=7)
    assert vm.end == NOW
    assert vm.segments == (
        ((a.fetched_at, 10), (b.fetched_at, 12)),
        ((c.fetched_at, 40),),
    )


def test_line_ticks_are_local_midnights() -> None:
    vm = line_vm([], NOW, TPE)
    assert [label for _, label in vm.ticks] == [
        "10/29", "10/30", "10/31", "11/01", "11/02", "11/03", "11/04",
    ]  # fmt: skip
    assert all(at.astimezone(TPE).hour == 0 for at, _ in vm.ticks)
    assert vm.segments == ()


def test_cycle_bars_take_peak_per_reset_and_mark_current() -> None:
    week1 = datetime(2026, 10, 28, 3, tzinfo=UTC)
    week2 = week1 + timedelta(days=7)
    week3 = week2 + timedelta(days=7)  # 還沒到 → 本期
    samples = [
        long(week1 - timedelta(days=3), 20, week1),
        long(week1 - timedelta(days=1), 75, week1 + timedelta(seconds=2)),  # 差幾秒也是同一期
        long(week2 - timedelta(days=1), 95, week2),
        long(NOW, 30, week3),
        session(NOW, 99),
    ]
    assert cycle_bars(samples, NOW, TPE) == (
        BarVM("10/28", 75, Level.WARN, False),
        BarVM("11/04", 95, Level.CRIT, False),
        BarVM("本期", 30, Level.OK, True),
    )


def test_cycle_bars_keep_only_the_latest_cycles() -> None:
    first = datetime(2026, 8, 1, tzinfo=UTC)
    samples = [long(first, i, first + timedelta(days=7 * i)) for i in range(MAX_CYCLES + 3)]
    bars = cycle_bars(samples, NOW, TPE)
    assert len(bars) == MAX_CYCLES
    assert bars[-1].percent == MAX_CYCLES + 2


def test_average_ignores_current_cycle_and_uses_last_four() -> None:
    def bar(p: float, current: bool = False) -> BarVM:
        return BarVM("x", p, Level.OK, current)

    assert average_text([bar(10), bar(60), bar(70), bar(80), bar(90), bar(5, True)]) == (
        "最近 4 個週期平均用到 75%"
    )
    assert average_text([bar(40), bar(50, True)]) is None  # 只有一期已結束
    assert average_text([bar(40), bar(61)], Lang.EN) == "Last 2 periods averaged 51%"


def test_build_service_usage_titles_follow_labels() -> None:
    reset = NOW + timedelta(days=20)
    usage = Usage(Window(label="5h"), Window(True, 6, reset, "30d"), fetched_at=NOW)
    state = ProviderState("codex", usage, None, False, "codex_cli")
    vm = build_service_usage(("codex", "Codex"), state, [long(NOW, 6, reset, "30d")], NOW, TPE)
    assert vm.title == "Codex"
    assert vm.line_title == "過去 7 天的 5 小時用量"
    assert vm.bars_title == "每個 30 天週期的最高用量"
    assert [line.percent for line in vm.lines] == ["0%", "6%"]
    assert vm.bars == (BarVM("本期", 6, Level.OK, True),)
    assert vm.average is None
    assert vm.error is None
    assert not vm.show_line  # 沒有 5h 視窗也沒有紀錄：不畫折線


def test_build_service_usage_without_state_uses_history_label() -> None:
    vm = build_service_usage(
        ("codex", "Codex"), None, [long(NOW, 6, NOW + timedelta(days=1), "30d")], NOW, TPE, Lang.EN
    )
    assert vm.lines == ()
    assert not vm.show_line
    assert vm.line_title == "5-hour usage, last 7 days"
    assert vm.bars_title == "Peak usage per 30-day period"
