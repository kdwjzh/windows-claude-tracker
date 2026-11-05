"""更新檢查的畫面：狀態文字、系統匣選單項目與藍點、「關於」頁、通知只發一次。"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fakes import FakeClock, FakeTransport
from usage_monitor.core import app_info
from usage_monitor.core.i18n import Lang
from usage_monitor.core.interfaces import Response
from usage_monitor.services.self_update import InstallError, InstallStatus
from usage_monitor.services.settings.store import SettingsStore
from usage_monitor.services.state_store import StateStore
from usage_monitor.services.update_check import UpdateChecker, UpdateState, UpdateStatus
from usage_monitor.ui.viewmodel import build_tray_vm, update_menu_text, update_status_text

NOW = datetime(2026, 10, 30, 9, tzinfo=UTC)
CURRENT = "0.10.0"


def state(status: UpdateStatus, latest: str | None = None, skipped: bool = False) -> UpdateState:
    return UpdateState(CURRENT, status, latest, skipped=skipped)


@pytest.mark.parametrize(
    ("value", "zh", "en"),
    [
        (None, "尚未檢查", "Not checked yet"),
        (state(UpdateStatus.UNKNOWN), "尚未檢查", "Not checked yet"),
        (state(UpdateStatus.CHECKING), "檢查中…", "Checking…"),
        (state(UpdateStatus.UP_TO_DATE), "已是最新版本", "You're up to date"),
        (state(UpdateStatus.UNAVAILABLE), "目前無法檢查", "Can't check right now"),
        (state(UpdateStatus.AVAILABLE, "1.0.0"), "有新版本 v1.0.0", "Version v1.0.0 is available"),
        (
            state(UpdateStatus.AVAILABLE, "1.0.0", skipped=True),
            "已略過 v1.0.0（有更新的版本時會再提醒）",
            "Skipped v1.0.0 (you'll be told about newer versions)",
        ),
    ],
)
def test_update_status_text(value: UpdateState | None, zh: str, en: str) -> None:
    assert update_status_text(value) == zh
    assert update_status_text(value, Lang.EN) == en


def test_update_menu_text_only_when_alerting() -> None:
    assert update_menu_text(state(UpdateStatus.AVAILABLE, "1.0.0")) == "有新版本 v1.0.0 →"
    assert update_menu_text(state(UpdateStatus.AVAILABLE, "1.0.0"), Lang.EN) == (
        "New version v1.0.0 →"
    )
    assert update_menu_text(state(UpdateStatus.AVAILABLE, "1.0.0", skipped=True)) is None
    assert update_menu_text(state(UpdateStatus.UNAVAILABLE)) is None
    assert update_menu_text(None) is None


def test_tray_blue_dot_flag() -> None:
    assert build_tray_vm([], {}, NOW, update_available=True).update_dot is True
    assert build_tray_vm([], {}, NOW).update_dot is False


# ---------------------------------------------------------------- Qt


def release(tag: str) -> Response:
    version = tag.removeprefix("v")
    assets = [
        {"name": n, "browser_download_url": f"{app_info.DOWNLOAD_PREFIX}{tag}/{n}"}
        for n in (app_info.exe_name(version), app_info.SUMS_NAME)
    ]
    body = {"tag_name": tag, "html_url": f"{app_info.RELEASES_URL}/tag/{tag}", "assets": assets}
    return Response(200, body=json.dumps(body).encode())


@pytest.fixture
def app(qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple]:
    pytest.importorskip("pytestqt")
    from usage_monitor.ui import controller as controller_module
    from usage_monitor.ui.controller import Controller

    opened: list[str] = []
    monkeypatch.setattr(controller_module.launch, "open_url", opened.append)
    store = SettingsStore(tmp_path / "settings.json")
    store.load()
    store.update(lambda s: replace(s, language="zh-TW"))
    transport = FakeTransport().add("GET", app_info.LATEST_RELEASE_API, release("v1.0.0"))
    updates = UpdateChecker(transport, FakeClock(NOW), store, CURRENT)
    downloads: list[tuple[UpdateState, Path]] = []
    quits: list[int] = []

    def download(update: UpdateState, folder: Path, on_percent: Callable[[int], None]) -> Path:
        downloads.append((update, folder))
        for p in (0, 0, 50, 100):  # 同一個百分比重複回報只送一次給畫面
            on_percent(p)
        if update.latest_version == "9.9.9":
            raise InstallError("SHA-256 不符")
        return folder / app_info.exe_name(update.latest_version or "")

    controller = Controller(
        qapp, store, StateStore(), [("claude", "Claude")], FakeClock(NOW),
        refresh=lambda: None, log_file=tmp_path / "m.log", on_quit=lambda: quits.append(1),
        updates=updates, download_update=download,
    )  # fmt: skip
    controller.test_downloads = downloads  # type: ignore[attr-defined]
    controller.test_quits = quits  # type: ignore[attr-defined]
    notes: list[tuple[str, str]] = []
    monkeypatch.setattr(controller.tray, "notify", lambda t, b: notes.append((t, b)))
    controller.start()
    yield controller, updates, store, notes, opened
    controller.shutdown()


@pytest.mark.qt
def test_new_version_shows_everywhere_and_notifies_once(app) -> None:
    controller, updates, store, notes, opened = app
    updates.check()  # 同一執行緒：bridge 直接送到 controller

    assert controller.tray._vm.update_dot is True  # pyright: ignore[reportPrivateUsage]
    assert controller.update_menu_label == "有新版本 v1.0.0 →"
    assert notes == [("用量監控有新版本 v1.0.0", "點這則通知查看並更新。")]
    assert store.current.update_check.notified_version == "1.0.0"

    controller.tray.notification_clicked.emit()  # 點通知 → 開「關於」頁（不是診斷）
    dialog = controller._dialog  # pyright: ignore[reportPrivateUsage]
    assert dialog is not None and dialog.nav.currentRow() == 3
    assert opened == []

    updates.check_now()
    updates._transport.add("GET", app_info.LATEST_RELEASE_API, release("v1.0.0"))  # type: ignore[attr-defined]  # pyright: ignore[reportPrivateUsage]
    updates.tick()
    assert len(notes) == 1  # 同一版不再通知


@pytest.mark.qt
def test_about_page_and_skip(app) -> None:
    controller, updates, store, _notes, _opened = app
    controller.open_settings()
    dialog = controller._dialog  # pyright: ignore[reportPrivateUsage]
    assert dialog is not None
    assert dialog.version_card.subtitle.text() == "尚未檢查"
    assert dialog.update_download.isHidden()  # 頁面沒切到也能檢查按鈕本身的顯示狀態

    updates.check()
    assert dialog.version_card.subtitle.text() == "有新版本 v1.0.0"
    assert not dialog.update_download.isHidden()
    assert dialog.update_skip.isEnabled()

    dialog.update_skip.click()
    assert store.current.update_check.skipped_version == "1.0.0"
    assert controller.update_menu_label is None
    assert controller.tray._vm.update_dot is False  # pyright: ignore[reportPrivateUsage]
    assert dialog.version_card.subtitle.text().startswith("已略過 v1.0.0")

    dialog.update_auto.switch.click()
    assert store.current.update_check.enabled is False


@pytest.mark.qt
def test_tray_menu_has_update_item_on_top(app) -> None:
    controller, updates, _store, _notes, opened = app
    menu = controller.tray._menu  # pyright: ignore[reportPrivateUsage]
    menu.aboutToShow.emit()
    assert not menu.actions()[0].isVisible()
    updates.check()
    menu.aboutToShow.emit()
    first = menu.actions()[0]
    assert first.isVisible() and first.text() == "有新版本 v1.0.0 →"
    first.trigger()  # 開「關於」頁（ADR 0007）；那裡才有「前往下載」與「立即更新」
    dialog = controller._dialog  # pyright: ignore[reportPrivateUsage]
    assert dialog is not None and dialog.nav.currentRow() == 3
    assert opened == []
    dialog.update_download.click()
    assert opened == [f"{app_info.RELEASES_URL}/tag/v1.0.0"]


@pytest.mark.qt
def test_auth_notification_click_still_runs_diagnose(app, monkeypatch: pytest.MonkeyPatch) -> None:
    from usage_monitor.core.errors import ErrKind, ErrReason, PollError
    from usage_monitor.core.models import ProviderState

    controller, _updates, _store, notes, _opened = app
    ran: list[int] = []
    monkeypatch.setattr(controller, "run_diagnose", lambda: ran.append(1))
    controller._states.update(  # pyright: ignore[reportPrivateUsage]
        ProviderState("claude", None, PollError(ErrKind.AUTH, "x", reason=ErrReason.NO_CREDENTIALS),
                      False, None)
    )  # fmt: skip
    assert notes and notes[-1][0] == "Claude 找不到登入資訊"
    controller.tray.notification_clicked.emit()
    assert ran == [1]  # 開主程式裡的診斷視窗（不再啟動外部的 diagnose.exe）


@pytest.mark.qt
def test_install_button_only_in_packaged_build(app) -> None:
    controller, updates, _store, _notes, _opened = app
    updates.check()
    controller.open_settings()
    dialog = controller._dialog  # pyright: ignore[reportPrivateUsage]
    assert dialog is not None
    assert controller.can_install_update is False  # 原始碼執行：只能前往下載
    assert dialog.update_install.isHidden()
    assert not dialog.update_download.isHidden()


@pytest.fixture
def packaged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Path, list]]:
    from usage_monitor.ui import controller as controller_module

    exe = tmp_path / "ClaudeUsageTracker-v0.10.0.exe"
    started: list[tuple[Path, Path]] = []
    monkeypatch.setattr(controller_module.relaunch, "frozen_exe", lambda: exe)
    monkeypatch.setattr(
        controller_module.relaunch, "start_replacement", lambda new, old: started.append((new, old))
    )
    yield exe, started


@pytest.mark.qt
def test_install_downloads_then_starts_new_version_and_quits(app, packaged, qtbot) -> None:
    controller, updates, _store, _notes, _opened = app
    exe, started = packaged
    updates.check()
    controller.open_settings()
    dialog = controller._dialog  # pyright: ignore[reportPrivateUsage]
    assert dialog is not None and not dialog.update_install.isHidden()

    percents: list[int] = []
    controller.install_progress.connect(percents.append)
    with qtbot.waitSignal(controller.install_finished, timeout=5000):
        dialog.update_install.click()
        assert controller.install_status is InstallStatus.DOWNLOADING
    ((state, folder),) = controller.test_downloads
    assert folder == exe.parent and state.latest_version == "1.0.0"
    assert percents == [0, 50, 100]
    # 先顯示「正在啟動」讓畫面重畫，再啟動新版（2026-11-06：之前畫面停在「正在下載」看不出進度）
    assert controller.install_status is InstallStatus.STARTING
    assert dialog.version_card.subtitle.text() == "正在啟動 v1.0.0…"
    assert not dialog.update_install.isEnabled()
    qtbot.waitUntil(lambda: controller.test_quits == [1], timeout=5000)
    assert started == [(exe.parent / "ClaudeUsageTracker-v1.0.0.exe", exe)]


@pytest.mark.qt
def test_install_failure_shows_message_and_keeps_running(app, packaged, qtbot) -> None:
    controller, updates, _store, _notes, _opened = app
    _exe, started = packaged
    updates._transport.add("GET", app_info.LATEST_RELEASE_API, release("v9.9.9"))  # type: ignore[attr-defined]  # pyright: ignore[reportPrivateUsage]
    updates.check()
    updates.check()  # 第二個回應：9.9.9（假的下載函式會失敗）
    controller.open_settings()
    dialog = controller._dialog  # pyright: ignore[reportPrivateUsage]
    assert dialog is not None

    with qtbot.waitSignal(controller.install_finished, timeout=5000):
        controller.install_update()
    assert controller.install_status is InstallStatus.FAILED
    assert dialog.version_card.subtitle.text() == "更新失敗，請按「前往下載」手動更新"
    assert dialog.update_install.isEnabled()  # 可以再試一次
    assert started == [] and controller.test_quits == []


@pytest.mark.qt
@pytest.mark.parametrize("updated_to", ["1.0.0", None])
def test_updated_notification_only_after_update(
    qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, updated_to: str | None
) -> None:
    """「立即更新」啟動的新版（--replaced）才通知「已更新到 vX」；平常啟動不通知。"""
    from usage_monitor.ui.controller import Controller

    store = SettingsStore(tmp_path / "settings.json")
    store.load()
    store.update(lambda s: replace(s, language="zh-TW"))
    controller = Controller(
        qapp, store, StateStore(), [("claude", "Claude")], FakeClock(NOW),
        refresh=lambda: None, log_file=tmp_path / "m.log", on_quit=lambda: None,
        updated_to=updated_to,
    )  # fmt: skip
    notes: list[tuple[str, str]] = []
    monkeypatch.setattr(controller.tray, "notify", lambda t, b: notes.append((t, b)))
    controller.start()
    try:
        if updated_to is None:
            assert notes == []
            return
        assert notes == [("用量監控已更新到 v1.0.0", "新版本已經在執行，點這則通知查看。")]
        controller.tray.notification_clicked.emit()  # 點通知 → 「關於」頁
        dialog = controller._dialog  # pyright: ignore[reportPrivateUsage]
        assert dialog is not None and dialog.nav.currentRow() == 3
    finally:
        controller.shutdown()
