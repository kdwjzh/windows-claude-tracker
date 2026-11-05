"""主程式裡的診斷視窗：背景執行、顯示結果、複製、出錯不當掉。"""

from __future__ import annotations

import threading
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("pytestqt")
# ubuntu CI 沒有 libEGL：整個檔案略過，改在 windows CI 跑（pytest 9 預設只略過找不到模組）
pytest.importorskip("PySide6.QtGui", exc_type=ImportError)

from PySide6.QtGui import QGuiApplication

from fakes import FakeClock
from usage_monitor.core.i18n import Lang
from usage_monitor.services.settings.store import SettingsStore
from usage_monitor.services.state_store import StateStore
from usage_monitor.ui import theme
from usage_monitor.ui.controller import Controller
from usage_monitor.ui.diagnose_window import DiagnoseWindow

pytestmark = pytest.mark.qt

NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)


def make(qtbot, run) -> DiagnoseWindow:  # type: ignore[no-untyped-def]
    window = DiagnoseWindow(run, Lang.ZH_TW, theme.DIALOG_DARK)
    qtbot.addWidget(window)
    return window


def test_shows_result_in_the_current_language(qtbot) -> None:
    langs: list[Lang] = []

    def run(lang: Lang) -> str:
        langs.append(lang)
        return "== 結論 ==\n  ✓ 可以正常取得用量"

    window = make(qtbot, run)
    window.show_and_run()
    qtbot.waitUntil(lambda: not window.running, timeout=3000)
    assert window.isVisible()
    assert "可以正常取得用量" in window.output.toPlainText()
    assert window.output.isReadOnly()
    assert window.copy.isEnabled() and window.rerun.isEnabled()
    assert langs == [Lang.ZH_TW]

    window.set_lang(Lang.EN)
    assert window.rerun.text() == "Run again"
    window.rerun.click()
    qtbot.waitUntil(lambda: not window.running, timeout=3000)
    assert langs == [Lang.ZH_TW, Lang.EN]


def test_buttons_are_disabled_while_running(qtbot) -> None:
    release = threading.Event()

    def run(_lang: Lang) -> str:
        release.wait(3)
        return "done"

    window = make(qtbot, run)
    window.show_and_run()
    assert window.running
    assert window.status.text() == "診斷中…"
    assert not window.copy.isEnabled() and not window.rerun.isEnabled()
    window.start()  # 跑的時候再按不會開第二個
    release.set()
    qtbot.waitUntil(lambda: not window.running, timeout=3000)
    assert window.output.toPlainText() == "done"
    assert window.status.text() == ""


def test_copy_puts_output_on_clipboard(qtbot) -> None:
    window = make(qtbot, lambda _lang: "診斷輸出")
    window.show_and_run()
    qtbot.waitUntil(lambda: not window.running, timeout=3000)
    window.copy.click()
    assert QGuiApplication.clipboard().text() == "診斷輸出"
    assert window.copy.text() == "已複製"


def test_exception_is_shown_not_raised(qtbot, caplog: pytest.LogCaptureFixture) -> None:
    def boom(_lang: Lang) -> str:
        raise RuntimeError("壞掉")

    window = make(qtbot, boom)
    window.show_and_run()
    qtbot.waitUntil(lambda: not window.running, timeout=3000)
    assert "RuntimeError" in window.output.toPlainText()
    assert window.rerun.isEnabled()
    assert "診斷執行失敗" in caplog.text


def test_close_only_hides(qtbot) -> None:
    window = make(qtbot, lambda _lang: "x")
    window.show_and_run()
    qtbot.waitUntil(lambda: not window.running, timeout=3000)
    window.close()
    assert not window.isVisible()


def test_controller_opens_window_with_ui_language(qapp, qtbot, tmp_path: Path) -> None:
    """儀表板「執行診斷」與通知共用 controller.run_diagnose：開主程式裡的視窗。"""
    store = SettingsStore(tmp_path / "settings.json")
    store.load()
    store.update(lambda s: replace(s, language="en"))
    langs: list[Lang] = []

    def run(lang: Lang) -> str:
        langs.append(lang)
        return "== Summary =="

    controller = Controller(
        qapp, store, StateStore(), [("claude", "Claude")], FakeClock(NOW),
        refresh=lambda: None, log_file=tmp_path / "m.log", on_quit=lambda: None, diagnose=run,
    )  # fmt: skip
    controller.start()
    try:
        controller.run_diagnose()
        window = controller._diagnose_window  # pyright: ignore[reportPrivateUsage]
        assert window is not None
        qtbot.waitUntil(lambda: not window.running, timeout=3000)
        assert window.output.toPlainText() == "== Summary =="
        assert window.windowTitle() == "Usage Monitor · Diagnostics"
        assert langs == [Lang.EN]
        store.update(lambda s: replace(s, language="zh-TW"))
        assert window.windowTitle() == "用量監控 · 診斷"  # 跟著介面換語言
    finally:
        controller.shutdown()


def test_controller_without_diagnose_does_nothing(qapp, tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    store.load()
    controller = Controller(
        qapp, store, StateStore(), [("claude", "Claude")], FakeClock(NOW),
        refresh=lambda: None, log_file=tmp_path / "m.log", on_quit=lambda: None,
    )  # fmt: skip
    controller.start()
    try:
        controller.run_diagnose()
        assert controller._diagnose_window is None  # pyright: ignore[reportPrivateUsage]
    finally:
        controller.shutdown()
