"""用量歷史紀錄（ROADMAP 第 5a 項）：sqlite3，只存百分比與時間。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fakes import FakeClock
from usage_monitor.core.errors import ErrKind, PollError
from usage_monitor.core.models import ProviderState, Usage, Window
from usage_monitor.services.history import RETENTION_DAYS, History, Sample
from usage_monitor.services.state_store import StateStore

T0 = datetime(2026, 11, 4, 12, tzinfo=UTC)
RESET = T0 + timedelta(hours=2)


def usage(at: datetime, session: float = 42, long: float = 18) -> Usage:
    return Usage(Window(True, session, RESET, "5h"), Window(True, long, None, "7d"), fetched_at=at)


def ok(at: datetime, pid: str = "claude", **kw: float) -> ProviderState:
    return ProviderState(pid, usage(at, **kw), error=None, stale=False, source_label="cli")


def make(tmp_path: Path) -> tuple[History, FakeClock]:
    clock = FakeClock(T0)
    return History(tmp_path / "history.db", clock), clock


def test_records_each_reported_window(tmp_path: Path) -> None:
    history, _ = make(tmp_path)
    history.record(ok(T0))
    assert history.samples("claude", T0 - timedelta(days=1)) == [
        Sample("claude", "session", "5h", T0, 42.0, RESET),
        Sample("claude", "long", "7d", T0, 18.0, None),
    ]


def test_skips_unreported_window(tmp_path: Path) -> None:
    """Codex 只有 30 天週期：沒回報的 5h 不記（不是 0%）。"""
    history, _ = make(tmp_path)
    u = Usage(Window(label="5h"), Window(True, 6, None, "30d"), fetched_at=T0)
    history.record(ProviderState("codex", u, None, False, "codex_cli"))
    assert [s.window for s in history.samples("codex", T0 - timedelta(days=1))] == ["long"]


def test_skips_errors_stale_and_repeats(tmp_path: Path) -> None:
    """失敗時 StateStore 仍帶著上一筆資料（stale），不能重複記成新的一筆。"""
    history, _ = make(tmp_path)
    history.record(ok(T0))
    history.record(ok(T0))  # 同一筆資料再通知一次
    stale = ProviderState("claude", usage(T0), PollError(ErrKind.TRANSIENT, "503"), True, None)
    history.record(stale)
    history.record(ProviderState("claude", None, PollError(ErrKind.AUTH, "x"), False, None))
    assert len(history.samples("claude", T0 - timedelta(days=1))) == 2


def test_samples_filter_by_provider_and_time_in_order(tmp_path: Path) -> None:
    history, clock = make(tmp_path)
    history.record(ok(T0, session=10))
    history.record(ok(T0, "codex"))
    history.record(ok(clock.advance(minutes=5), session=20))
    rows = history.samples("claude", T0 + timedelta(minutes=1))
    assert [(r.window, r.percent) for r in rows] == [("session", 20.0), ("long", 18.0)]
    assert {r.provider_id for r in history.samples("codex", T0)} == {"codex"}


def test_old_samples_are_pruned(tmp_path: Path) -> None:
    history, clock = make(tmp_path)
    history.record(ok(T0))
    later = clock.advance(days=RETENTION_DAYS + 1)
    history.record(ok(later))
    assert [r.fetched_at for r in history.samples("claude", T0 - timedelta(days=1))] == [
        later,
        later,
    ]


def test_survives_reopen(tmp_path: Path) -> None:
    history, clock = make(tmp_path)
    history.record(ok(T0))
    again = History(tmp_path / "history.db", clock)
    assert len(again.samples("claude", T0 - timedelta(days=1))) == 2


def test_clear_deletes_everything(tmp_path: Path) -> None:
    history, clock = make(tmp_path)
    history.record(ok(T0))
    history.clear()
    assert history.samples("claude", T0 - timedelta(days=1)) == []
    history.record(ok(clock.advance(minutes=5)))  # 清除後照常記錄
    assert len(history.samples("claude", T0 - timedelta(days=1))) == 2


def test_broken_file_never_raises(tmp_path: Path) -> None:
    """壞掉的檔案（或寫不進去）只記 log，不影響輪詢；清除可以讓它恢復。"""
    path = tmp_path / "history.db"
    path.write_bytes(b"not a database" * 100)
    history = History(path, FakeClock(T0))
    history.record(ok(T0))
    assert history.samples("claude", T0 - timedelta(days=1)) == []
    history.clear()
    history.record(ok(T0 + timedelta(minutes=5)))
    assert len(history.samples("claude", T0 - timedelta(days=1))) == 2


def test_subscribes_to_state_store(tmp_path: Path) -> None:
    history, _ = make(tmp_path)
    store = StateStore()
    store.subscribe(history.record)
    store.update(ok(T0))
    assert len(history.samples("claude", T0 - timedelta(days=1))) == 2
