"""排程：用 FakeProvider＋FakeClock 直接呼叫 tick()，不需要真的等待。"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest

from fakes import FakeClock, FakeProvider
from usage_monitor.core.errors import ErrKind, PollError
from usage_monitor.core.models import ProviderState, Usage, Window
from usage_monitor.services.scheduler import (
    Scheduler,
    backoff_seconds,
    next_after_success,
)
from usage_monitor.services.state_store import StateStore

T0 = datetime(2026, 10, 29, 12, tzinfo=UTC)
INTERVAL = 300.0


def usage(resets_in: timedelta | None = None, percent: float = 42) -> Usage:
    resets = T0 + resets_in if resets_in else None
    return Usage(Window(True, percent, resets, "5h"), Window(True, 18, None, "7d"), T0)


def transient(retry_after: float | None = None) -> PollError:
    return PollError(ErrKind.TRANSIENT, "HTTP 503", status=503, retry_after=retry_after)


def auth() -> PollError:
    return PollError(ErrKind.AUTH, "找不到登入資訊")


class Harness:
    def __init__(self, *providers: FakeProvider) -> None:
        self.clock = FakeClock(T0)
        self.store = StateStore()
        self.scheduler = Scheduler(
            list(providers), self.store, self.clock, interval_minutes=INTERVAL / 60
        )

    def tick(self) -> float:
        """跑一次，回傳距離下次醒來的秒數。"""
        return (self.scheduler.tick() - self.clock.now()).total_seconds()

    def state(self, pid: str) -> ProviderState:
        result = self.store.get(pid)
        assert result is not None
        return result


# ---------------------------------------------------------------- 純函式


@pytest.mark.parametrize(
    ("retries", "retry_after", "expected"),
    [
        (1, None, 30),
        (2, None, 60),
        (3, None, 120),
        (4, None, 240),
        (5, None, 300),
        (9, None, 300),
        (1, 600.0, 600),
        (3, 10.0, 120),
        (0, None, 30),
    ],
)
def test_backoff_seconds(retries: int, retry_after: float | None, expected: float) -> None:
    assert backoff_seconds(retries, INTERVAL, retry_after) == expected


def test_next_after_success_defaults_to_interval() -> None:
    assert next_after_success(usage(), T0, INTERVAL) == T0 + timedelta(seconds=300)


def test_next_after_success_polls_right_after_reset() -> None:
    u = usage(timedelta(minutes=2))
    assert next_after_success(u, T0, INTERVAL) == T0 + timedelta(minutes=2, seconds=10)


def test_next_after_success_ignores_past_and_far_resets() -> None:
    assert next_after_success(usage(timedelta(minutes=-1)), T0, INTERVAL) == T0 + timedelta(
        seconds=300
    )
    assert next_after_success(usage(timedelta(hours=3)), T0, INTERVAL) == T0 + timedelta(
        seconds=300
    )


def test_next_after_success_has_minimum_delay() -> None:
    u = usage(timedelta(seconds=-9))  # 剛過重置（resets_at+10 仍在未來，但非常近）
    u = Usage(Window(True, 0, T0 - timedelta(seconds=9), "5h"), u.long, T0)
    assert next_after_success(u, T0, INTERVAL) == T0 + timedelta(seconds=300)
    soon = Usage(Window(True, 0, T0 + timedelta(seconds=1), "5h"), u.long, T0)
    assert next_after_success(soon, T0, INTERVAL) == T0 + timedelta(seconds=11)


# ---------------------------------------------------------------- 成功


def test_first_tick_polls_and_publishes() -> None:
    p = FakeProvider("claude", [usage()], source="桌面版")
    h = Harness(p)
    assert h.tick() == 300
    s = h.state("claude")
    assert s.usage == usage()
    assert (s.error, s.stale, s.source_label) == (None, False, "桌面版")


def test_not_polled_before_due() -> None:
    p = FakeProvider("claude", [usage()])
    h = Harness(p)
    h.tick()
    h.clock.advance(299)
    assert h.tick() == 1
    assert p.poll_count == 1
    h.clock.advance(1)
    h.tick()
    assert p.poll_count == 2


def test_reset_soon_schedules_early_poll() -> None:
    h = Harness(FakeProvider("claude", [usage(timedelta(minutes=1))]))
    assert h.tick() == 70


# ---------------------------------------------------------------- 暫時性錯誤


def test_transient_backoff_then_recovery_resets_retries() -> None:
    p = FakeProvider("claude", [transient(), transient(), transient(), usage(), transient()])
    h = Harness(p)
    delays = []
    for _ in range(4):
        delays.append(h.tick())
        h.clock.advance(delays[-1])
    assert delays == [30, 60, 120, 300]
    assert h.tick() == 30  # 成功後重新從 30 秒開始


def test_retry_after_wins_when_larger() -> None:
    h = Harness(FakeProvider("claude", [transient(retry_after=900)]))
    assert h.tick() == 900


def test_failure_keeps_last_usage_as_stale() -> None:
    p = FakeProvider("claude", [usage(), transient(), usage(percent=50)])
    h = Harness(p)
    h.tick()
    h.clock.advance(300)
    h.tick()
    s = h.state("claude")
    assert s.usage == usage()
    assert s.stale is True
    assert s.error is not None and s.error.kind is ErrKind.TRANSIENT

    h.clock.advance(30)
    h.tick()
    s = h.state("claude")
    assert s.usage is not None and s.usage.session.percent == 50
    assert (s.stale, s.error) == (False, None)


def test_failure_without_previous_usage_is_not_stale() -> None:
    h = Harness(FakeProvider("claude", [transient()]))
    h.tick()
    s = h.state("claude")
    assert (s.usage, s.stale) == (None, False)


def test_unsupported_is_retried_like_transient() -> None:
    h = Harness(FakeProvider("claude", [PollError(ErrKind.UNSUPPORTED, "404", status=404)]))
    assert h.tick() == 30


# ---------------------------------------------------------------- 認證錯誤


def test_auth_error_pauses_until_signature_changes() -> None:
    p = FakeProvider("claude", [auth(), usage()], signature="logged-out")
    h = Harness(p)
    assert h.tick() == 60
    assert h.state("claude").error is not None

    for _ in range(3):  # 簽章沒變：每分鐘只比對簽章，不打 API
        h.clock.advance(60)
        assert h.tick() == 60
    assert p.poll_count == 1

    p.signature = "logged-in"
    h.clock.advance(60)
    assert h.tick() == 300
    assert p.poll_count == 2
    assert h.state("claude").error is None


def test_auth_error_keeps_usage_stale() -> None:
    p = FakeProvider("claude", [usage(), auth()])
    h = Harness(p)
    h.tick()
    h.clock.advance(300)
    h.tick()
    s = h.state("claude")
    assert s.stale and s.usage == usage()
    assert s.error is not None and s.error.kind is ErrKind.AUTH


def test_refresh_now_polls_even_when_paused_or_not_due() -> None:
    p = FakeProvider("claude", [auth(), usage()])
    h = Harness(p)
    h.tick()
    h.scheduler.refresh_now()
    h.tick()
    assert p.poll_count == 2
    h.scheduler.refresh_now()
    h.tick()  # 剛成功、還沒到期，手動更新仍會打
    assert p.poll_count == 3


def test_signature_failure_is_contained() -> None:
    class BadSignature(FakeProvider):
        def credential_signature(self) -> str:
            raise OSError("boom")

    p = BadSignature("claude", [auth()])
    h = Harness(p)
    h.tick()
    h.clock.advance(60)
    h.tick()
    assert p.poll_count == 1  # 簽章一直是 ""，維持暫停


# ---------------------------------------------------------------- 錯誤隔離


def test_providers_are_isolated() -> None:
    broken = FakeProvider("claude", [RuntimeError("bug")])
    healthy = FakeProvider("codex", [usage()])
    h = Harness(broken, healthy)
    assert h.tick() == 30
    claude = h.state("claude")
    assert claude.error is not None
    assert claude.error.kind is ErrKind.TRANSIENT
    assert "RuntimeError" in claude.error.message
    assert h.state("codex").error is None


def test_independent_schedules() -> None:
    claude = FakeProvider("claude", [transient()])
    codex = FakeProvider("codex", [usage()])
    h = Harness(claude, codex)
    h.tick()
    h.clock.advance(30)
    h.tick()  # 只有 claude 到期
    assert (claude.poll_count, codex.poll_count) == (2, 1)


def test_source_label_failure_is_contained() -> None:
    class BadSource(FakeProvider):
        def source_label(self) -> str | None:
            raise RuntimeError("boom")

    h = Harness(BadSource("claude", [usage()]))
    h.tick()
    assert h.state("claude").source_label is None


def test_no_providers_idles_for_interval() -> None:
    h = Harness()
    assert h.tick() == 300


def test_set_providers_keeps_existing_and_polls_new_immediately() -> None:
    claude = FakeProvider("claude", [transient()])
    codex = FakeProvider("codex", [usage()])
    h = Harness(claude)
    h.tick()  # claude 進入退避，30 秒後才重試
    h.scheduler.set_providers([claude, codex])
    assert h.tick() == 30  # codex 立刻輪詢；claude 的退避狀態保留
    assert (claude.poll_count, codex.poll_count) == (1, 1)


def test_set_providers_removes_service() -> None:
    claude = FakeProvider("claude", [usage()])
    codex = FakeProvider("codex", [usage()])
    h = Harness(claude, codex)
    h.tick()
    h.scheduler.set_providers([codex])
    h.clock.advance(300)
    h.tick()
    assert (claude.poll_count, codex.poll_count) == (1, 2)


def test_set_providers_to_empty_idles() -> None:
    h = Harness(FakeProvider("claude", [usage()]))
    h.scheduler.set_providers([])
    assert h.tick() == 300


def test_set_interval_applies_to_next_schedule() -> None:
    h = Harness(FakeProvider("claude", [usage()]))
    h.scheduler.set_interval(10)
    assert h.scheduler.interval_seconds == 600
    assert h.tick() == 600


# ---------------------------------------------------------------- 執行緒


def test_thread_polls_on_start_and_refresh() -> None:
    p = FakeProvider("claude", [usage()])
    clock = FakeClock(T0)
    store = StateStore()
    updated = threading.Event()
    store.subscribe(lambda _: updated.set())
    scheduler = Scheduler([p], store, clock)
    scheduler.start()
    scheduler.start()  # 重複 start 不會開第二條執行緒
    try:
        assert updated.wait(5)
        updated.clear()
        scheduler.refresh_now()
        assert updated.wait(5)
        assert p.poll_count == 2
    finally:
        scheduler.stop()
    assert scheduler._thread is not None  # pyright: ignore[reportPrivateUsage]
    assert not scheduler._thread.is_alive()  # pyright: ignore[reportPrivateUsage]


def test_stop_without_start() -> None:
    Scheduler([], StateStore(), FakeClock(T0)).stop()


def test_thread_survives_tick_crash() -> None:
    class Exploding(Scheduler):
        calls = 0

        def tick(self) -> datetime:
            Exploding.calls += 1
            if Exploding.calls == 1:
                raise RuntimeError("boom")
            done.set()
            return super().tick()

    done = threading.Event()
    scheduler = Exploding([], StateStore(), FakeClock(T0))
    scheduler.start()
    try:
        scheduler.refresh_now()
        assert done.wait(5)
    finally:
        scheduler.stop()
