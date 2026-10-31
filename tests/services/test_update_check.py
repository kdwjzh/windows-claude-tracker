"""更新檢查：用 FakeTransport 模擬 GitHub 回應、FakeClock 驗證排程，不連網路。"""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fakes import FakeClock, FakeTransport
from usage_monitor.core import app_info
from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.interfaces import Response
from usage_monitor.services.settings.store import SettingsStore
from usage_monitor.services.update_check import (
    CHECK_INTERVAL,
    IDLE_WAKE,
    STARTUP_DELAY,
    UpdateChecker,
    UpdateState,
    UpdateStatus,
)

T0 = datetime(2026, 10, 30, 9, tzinfo=UTC)
API = app_info.LATEST_RELEASE_API
CURRENT = "0.10.0"


def release(tag: str = "v1.0.0", **extra: object) -> Response:
    body = {"tag_name": tag, "html_url": f"{app_info.RELEASES_URL}/tag/{tag}", **extra}
    return Response(200, body=json.dumps(body).encode())


class Harness:
    def __init__(self, tmp_path: Path, *results: Response | BaseException) -> None:
        self.clock = FakeClock(T0)
        self.transport = FakeTransport().add("GET", API, *results)
        self.store = SettingsStore(tmp_path / "settings.json")
        self.store.load()
        self.checker = UpdateChecker(self.transport, self.clock, self.store, CURRENT)
        self.seen: list[UpdateState] = []
        self.checker.subscribe(self.seen.append)

    def tick(self) -> float:
        return (self.checker.tick() - self.clock.now()).total_seconds()


# ---------------------------------------------------------------- 結果


def test_new_version_available(tmp_path: Path) -> None:
    h = Harness(tmp_path, release("v1.0.0"))
    state = h.checker.check()
    assert state == UpdateState(
        current_version=CURRENT,
        status=UpdateStatus.AVAILABLE,
        latest_version="1.0.0",
        url=f"{app_info.RELEASES_URL}/tag/v1.0.0",
    )
    assert state.should_alert
    assert [s.status for s in h.seen] == [UpdateStatus.CHECKING, UpdateStatus.AVAILABLE]
    assert h.store.current.update_check.last_checked_at == T0.isoformat()


def test_request_has_no_token(tmp_path: Path) -> None:
    h = Harness(tmp_path, release())
    h.checker.check()
    headers = h.transport.calls[0].headers
    assert not any(k.lower() == "authorization" for k in headers)
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["User-Agent"] == f"windows-claude-tracker/{CURRENT}"
    assert h.transport.calls[0].timeout == 30


@pytest.mark.parametrize(
    "resp",
    [
        release(f"v{CURRENT}"),  # 同版
        release("v0.9.0"),  # 比較舊
        release("v1.0.0-beta.1"),  # pre-release 不算
        release("v1.0.0", prerelease=True),
        release("v1.0.0", draft=True),
        release("not-a-version"),
        Response(200, body=json.dumps({"no_tag": 1}).encode()),
    ],
)
def test_up_to_date(tmp_path: Path, resp: Response) -> None:
    state = Harness(tmp_path, resp).checker.check()
    assert state.status is UpdateStatus.UP_TO_DATE
    assert not state.should_alert


@pytest.mark.parametrize(
    "result",
    [
        Response(404),  # 尚無 Release 或 API 暫時無法使用
        Response(403),
        Response(429),
        Response(500),
        Response(200, body=b"<html>"),
        Response(200, body=b"[]"),
        PollError(ErrKind.TRANSIENT, "連線失敗", reason=ErrReason.NETWORK),
    ],
)
def test_cannot_check_is_quiet(tmp_path: Path, result: Response | BaseException) -> None:
    h = Harness(tmp_path, result)
    state = h.checker.check()
    assert state.status is UpdateStatus.UNAVAILABLE
    assert not state.should_alert
    assert h.checker.claim_notification() is None  # 不發通知
    assert h.store.current.update_check.last_checked_at is None


def test_failure_after_finding_update_keeps_alert(tmp_path: Path) -> None:
    h = Harness(tmp_path, release("v1.0.0"), Response(503))
    h.checker.check()
    state = h.checker.check()
    assert state.status is UpdateStatus.AVAILABLE and state.latest_version == "1.0.0"


def test_untrusted_release_url_is_replaced(tmp_path: Path) -> None:
    resp = Response(200, body=json.dumps(
        {"tag_name": "v2.0.0", "html_url": "https://evil.example/download"}).encode())  # fmt: skip
    assert Harness(tmp_path, resp).checker.check().url == app_info.RELEASES_URL


# ---------------------------------------------------------------- 略過與通知


def test_skip_version_then_newer_version_alerts_again(tmp_path: Path) -> None:
    h = Harness(tmp_path, release("v1.0.0"), release("v1.0.0"), release("v1.1.0"))
    h.checker.check()
    h.checker.skip_latest()
    assert h.store.current.update_check.skipped_version == "1.0.0"
    assert h.checker.state.skipped and not h.checker.state.should_alert
    assert h.checker.check().skipped  # 再查一次仍是略過
    newer = h.checker.check()
    assert newer.latest_version == "1.1.0" and newer.should_alert


def test_skip_without_known_version_does_nothing(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.checker.skip_latest()
    assert h.store.current.update_check.skipped_version is None


def test_notification_only_once_per_version(tmp_path: Path) -> None:
    h = Harness(tmp_path, release("v1.0.0"), release("v1.0.0"), release("v1.1.0"))
    h.checker.check()
    assert h.checker.claim_notification() == "1.0.0"
    assert h.checker.claim_notification() is None
    h.checker.check()
    assert h.checker.claim_notification() is None  # 重新查到同一版也不再通知
    h.checker.check()
    assert h.checker.claim_notification() == "1.1.0"


def test_notification_remembered_across_restart(tmp_path: Path) -> None:
    h = Harness(tmp_path, release("v1.0.0"))
    h.checker.check()
    assert h.checker.claim_notification() == "1.0.0"
    again = Harness(tmp_path, release("v1.0.0"))  # 重開程式：同一個設定檔
    again.checker.check()
    assert again.checker.claim_notification() is None


def test_settings_changed_reapplies_skip(tmp_path: Path) -> None:
    h = Harness(tmp_path, release("v1.0.0"))
    h.checker.check()
    h.store.update(lambda s: replace(s, update_check=replace(s.update_check,
                                                             skipped_version="1.0.0")))  # fmt: skip
    h.checker.settings_changed()
    assert h.checker.state.skipped


# ---------------------------------------------------------------- 排程


def test_first_check_30_seconds_after_start_then_every_24_hours(tmp_path: Path) -> None:
    h = Harness(tmp_path, release(f"v{CURRENT}"), release(f"v{CURRENT}"))
    assert h.tick() == STARTUP_DELAY.total_seconds()
    assert h.transport.calls == []
    h.clock.advance(30)
    assert h.tick() == CHECK_INTERVAL.total_seconds()
    assert len(h.transport.calls) == 1
    h.clock.advance(hours=23)
    h.tick()
    assert len(h.transport.calls) == 1
    h.clock.advance(hours=1)
    h.tick()
    assert len(h.transport.calls) == 2


def test_disabled_only_checks_when_asked(tmp_path: Path) -> None:
    h = Harness(tmp_path, release("v1.0.0"))
    h.store.update(lambda s: replace(s, update_check=replace(s.update_check, enabled=False)))
    h.clock.advance(days=3)
    assert h.tick() == IDLE_WAKE.total_seconds()
    assert h.transport.calls == []
    h.checker.check_now()
    h.tick()
    assert len(h.transport.calls) == 1
    assert h.checker.state.status is UpdateStatus.AVAILABLE


def test_thread_checks_on_demand(tmp_path: Path) -> None:
    h = Harness(tmp_path, release("v1.0.0"))
    done = threading.Event()
    h.checker.subscribe(lambda s: done.set() if s.status is UpdateStatus.AVAILABLE else None)
    h.checker.start()
    h.checker.start()
    try:
        h.checker.check_now()
        assert done.wait(5)
    finally:
        h.checker.stop()


def test_thread_survives_errors(tmp_path: Path) -> None:
    class Exploding(UpdateChecker):
        calls = 0

        def tick(self) -> datetime:
            Exploding.calls += 1
            if Exploding.calls == 1:
                raise RuntimeError("boom")
            ok.set()
            return super().tick()

    ok = threading.Event()
    store = SettingsStore(tmp_path / "s.json")
    store.load()
    checker = Exploding(FakeTransport(), FakeClock(T0), store, CURRENT)
    checker.start()
    try:
        checker.check_now()
        assert ok.wait(5)
    finally:
        checker.stop()


def test_settings_write_failure_is_contained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = Harness(tmp_path, release("v1.0.0"))

    def fail(_change: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(h.store, "update", fail)
    assert h.checker.check().status is UpdateStatus.AVAILABLE
    assert h.checker.claim_notification() == "1.0.0"


def test_stop_without_start(tmp_path: Path) -> None:
    Harness(tmp_path).checker.stop()
    assert T0 + timedelta(0) == T0
