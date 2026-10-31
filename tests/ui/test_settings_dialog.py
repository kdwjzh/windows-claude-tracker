"""設定視窗（畫板 5）：每個選項改了立即寫進設定並生效；外部改設定時畫面同步。

不碰「開機時啟動」開關（會改到真的登錄檔）。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt

from fakes import FakeClock
from usage_monitor.core.errors import ErrKind, PollError
from usage_monitor.core.i18n import Lang
from usage_monitor.core.models import ProviderState, Usage, Window
from usage_monitor.services.settings.store import SettingsStore
from usage_monitor.services.state_store import StateStore
from usage_monitor.ui import theme
from usage_monitor.ui.controller import Controller
from usage_monitor.ui.settings_dialog.dialog import THEME_CHOICES, SettingsDialog
from usage_monitor.ui.settings_dialog.widgets import hotkey_text

pytestmark = pytest.mark.qt

NOW = datetime(2026, 10, 29, 10, tzinfo=UTC)
CATALOG = [("claude", "Claude"), ("codex", "Codex")]
K = Qt.KeyboardModifier


@pytest.mark.parametrize(
    ("key", "mods", "text"),
    [
        (Qt.Key.Key_U, K.ControlModifier | K.AltModifier, "Ctrl+Alt+U"),
        (Qt.Key.Key_5, K.ControlModifier | K.ShiftModifier, "Ctrl+Shift+5"),
        (Qt.Key.Key_F9, K.MetaModifier, "Win+F9"),
        (Qt.Key.Key_U, K.NoModifier, None),  # 沒有修飾鍵
        (Qt.Key.Key_Control, K.ControlModifier, None),  # 只按修飾鍵
        (Qt.Key.Key_Return, K.ControlModifier, None),  # 不支援的鍵
    ],
)
def test_hotkey_text(key: Qt.Key, mods: Qt.KeyboardModifier, text: str | None) -> None:
    assert hotkey_text(int(key.value), mods) == text


@pytest.fixture
def setup(qapp, tmp_path: Path) -> Iterator[tuple[Controller, SettingsStore, StateStore]]:
    store = SettingsStore(tmp_path / "settings.json")
    store.load()
    # 斷言用的是中文：明確指定語言，不依賴這台機器的 Windows 語言（CI runner 是英文）
    store.update(lambda s: replace(s, language="zh-TW"))
    states = StateStore()
    controller = Controller(
        qapp,
        store,
        states,
        CATALOG,
        FakeClock(NOW),
        refresh=lambda: None,
        log_file=tmp_path / "monitor.log",
        on_quit=lambda: None,
    )
    controller.start()
    controller.open_settings()
    yield controller, store, states
    controller.shutdown()


def dialog_of(controller: Controller) -> SettingsDialog:
    dialog = controller._dialog  # pyright: ignore[reportPrivateUsage]
    assert dialog is not None
    return dialog


def test_dialog_opens_once_and_close_only_hides(setup) -> None:
    controller, _, _ = setup
    dialog = dialog_of(controller)
    assert dialog.isVisible()
    assert dialog.windowTitle() == "用量監控 · 設定"
    assert [dialog.nav.item(i).text() for i in range(dialog.nav.count())] == [
        "一般",
        "進階",
        "關於",
    ]
    dialog.close()
    assert not dialog.isVisible()
    controller.open_settings()
    assert dialog_of(controller) is dialog and dialog.isVisible()


def test_interval_change_is_saved_immediately(setup) -> None:
    controller, store, _ = setup
    combo = dialog_of(controller).interval
    combo.setCurrentIndex(combo.findData(15))
    assert store.current.interval_minutes == 15
    assert '"interval_minutes": 15' in store.path.read_text(encoding="utf-8")


def test_widget_switches_apply_immediately(setup) -> None:
    controller, store, _ = setup
    dialog = dialog_of(controller)
    dialog.locked.switch.click()
    assert store.current.widget.locked is True
    assert controller.widget.vm.locked is True
    dialog.visible.switch.click()
    assert store.current.widget.visible is False
    assert not controller.widget.isVisible()
    dialog.fullscreen.switch.click()
    assert store.current.widget.hide_on_fullscreen is False


def test_opacity_slider_is_debounced(setup, qtbot) -> None:
    controller, store, _ = setup
    dialog = dialog_of(controller)
    dialog.opacity.setValue(60)
    dialog.opacity.setValue(75)
    assert dialog.opacity_value.text() == "75%"
    qtbot.waitUntil(lambda: store.current.widget.opacity == 0.75, timeout=2000)


def test_theme_change_restyles(setup) -> None:
    controller, store, _ = setup
    dialog = dialog_of(controller)
    dialog.theme.setCurrentIndex([v for v, _ in THEME_CHOICES].index("light"))
    assert store.current.widget.theme == "light"
    assert theme.DIALOG_LIGHT.window in dialog.styleSheet()


def test_service_toggle_enables_codex_column(setup) -> None:
    controller, store, _ = setup
    _, codex_switch = dialog_of(controller).service_cards["codex"]
    codex_switch.switch.click()
    assert store.current.providers == ("claude", "codex")
    assert [c.provider_id for c in controller.widget.vm.columns] == ["claude", "codex"]
    claude_switch = dialog_of(controller).service_cards["claude"][1]
    claude_switch.switch.click()
    assert store.current.providers == ("codex",)


def test_hotkey_capture_saves_and_reports_failure(setup) -> None:
    controller, store, _ = setup
    dialog = dialog_of(controller)
    dialog.hotkey_button.captured.emit("Ctrl+Alt+K")
    assert store.current.widget.hotkey == "Ctrl+Alt+K"
    assert dialog.hotkey_label.text() == "Ctrl + Alt + K"
    if not controller.hotkey_registered:  # 非 Windows 或被占用時要提示
        assert "無法使用" in dialog.hotkey_card.subtitle.text()


def test_language_switch_applies_immediately(setup) -> None:
    """階段 6.5 驗收：切換語言後，小工具、選單、設定視窗立即變成該語言。"""
    controller, store, _ = setup
    old_dialog = dialog_of(controller)
    old_dialog.nav.setCurrentRow(1)
    old_dialog.language.setCurrentIndex(old_dialog.language.findData("en"))
    assert store.current.language == "en"
    assert controller.lang is Lang.EN

    dialog = dialog_of(controller)
    assert dialog is not old_dialog  # 依新語言重建
    assert dialog.isVisible()
    assert dialog.nav.currentRow() == 1  # 留在原本的頁面
    assert dialog.windowTitle() == "Usage Monitor · Settings"
    assert dialog.nav.item(0).text() == "General"
    assert dialog.interval.currentText() == "Every 5 min"
    assert dialog.visible.label.text() == "On"
    assert controller.widget.vm.columns[0].note == "Loading…"
    assert controller.widget_menu.actions()[0].text().startswith("Refresh now")

    dialog.language.setCurrentIndex(dialog.language.findData("zh-TW"))
    assert controller.lang is Lang.ZH_TW
    assert dialog_of(controller).windowTitle() == "用量監控 · 設定"
    assert controller.widget.vm.columns[0].note == "讀取中…"


def test_system_language_follows_windows(qapp, tmp_path: Path) -> None:
    """預設 "system"：這裡的 Windows 被固定成英文（tests/ui/conftest.py），介面應該是英文。"""
    store = SettingsStore(tmp_path / "settings.json")
    store.load()
    assert store.current.language == "system"
    controller = Controller(
        qapp, store, StateStore(), CATALOG, FakeClock(NOW),
        refresh=lambda: None, log_file=tmp_path / "m.log", on_quit=lambda: None,
    )  # fmt: skip
    try:
        assert controller.lang is Lang.EN
        assert controller.widget.vm.columns[0].note == "Loading…"
    finally:
        controller.shutdown()


def test_language_dropdown_lists_choices(setup) -> None:
    controller, _, _ = setup
    combo = dialog_of(controller).language
    assert [combo.itemData(i) for i in range(combo.count())] == ["system", "zh-TW", "en"]
    assert [combo.itemText(i) for i in range(1, 3)] == ["繁體中文", "English"]


def test_cli_refresh_switch(setup) -> None:
    controller, store, _ = setup
    dialog_of(controller).cli_refresh.switch.click()
    assert store.current.allow_cli_refresh is True


def test_external_changes_sync_back(setup) -> None:
    """右鍵選單改了鎖定、或手動改設定時，設定視窗跟著更新，且不會反過來再寫一次。"""
    controller, store, _ = setup
    dialog = dialog_of(controller)
    controller.set_locked(True)
    assert dialog.locked.isChecked()
    assert dialog.locked.label.text() == "開啟"
    store.update(lambda s: replace(s, interval_minutes=7))
    assert dialog.interval.currentData() == 7  # 不在選項裡的值也會顯示


def test_service_status_lines(setup) -> None:
    controller, store, states = setup
    store.update(lambda s: replace(s, providers=("claude", "codex")))
    usage = Usage(Window(True, 42, None, "5h"), Window(True, 18, None, "7d"), NOW)
    states.update(ProviderState("claude", usage, None, False, "桌面版"))
    states.update(ProviderState("codex", None, PollError(ErrKind.AUTH, "找不到 Codex 登入資訊"),
                                False, None))  # fmt: skip
    cards = dialog_of(controller).service_cards
    assert cards["claude"][0].subtitle.text() == "已連線 · 來源：桌面版"
    assert cards["claude"][0].subtitle.objectName() == "statusOk"
    assert cards["codex"][0].subtitle.text() == "未登入 · 找不到 Codex 登入資訊"
    assert cards["codex"][0].subtitle.objectName() == "statusError"


def test_close_flushes_pending_opacity(setup) -> None:
    controller, store, _ = setup
    dialog = dialog_of(controller)
    dialog.opacity.setValue(50)
    dialog.close()
    assert store.current.widget.opacity == 0.5


def test_broken_settings_file_starts_with_defaults(qapp, tmp_path: Path) -> None:
    """階段 6 驗收：手動改壞 settings.json 時仍能用預設值啟動。"""
    path = tmp_path / "settings.json"
    path.write_text("{ 壞掉", encoding="utf-8")
    store = SettingsStore(path)
    store.load()
    controller = Controller(
        qapp, store, StateStore(), CATALOG, FakeClock(NOW),
        refresh=lambda: None, log_file=tmp_path / "m.log", on_quit=lambda: None,
    )  # fmt: skip
    controller.open_settings()
    try:
        assert dialog_of(controller).interval.currentData() == 5
        assert (tmp_path / "settings.json.broken").exists()
    finally:
        controller.shutdown()


def test_about_page_shows_license_and_disclaimer(setup) -> None:
    controller, store, _ = setup
    dialog = dialog_of(controller)
    assert "與 Anthropic、OpenAI 無關" in dialog.disclaimer.text()
    store.update(lambda s: replace(s, language="en"))
    assert "not affiliated with Anthropic or OpenAI" in dialog_of(controller).disclaimer.text()
