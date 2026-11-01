"""把小工具、系統匣、懸停卡、設定與排程接在一起（主執行緒）。

負責：依狀態重畫、顯示／隱藏（手動與全螢幕分開記錄）、拖曳貼齊與位置存取、
螢幕變更、主題、全域快捷鍵、定期重設 TOPMOST、認證錯誤通知。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter, QLocale, QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtWidgets import QApplication

from usage_monitor.core import app_info
from usage_monitor.core.i18n import Lang, resolve_language, t
from usage_monitor.core.interfaces import Clock
from usage_monitor.core.models import ProviderState
from usage_monitor.platform import autostart, fullscreen, hotkey, launch, topmost
from usage_monitor.services.settings.schema import Settings, WidgetSettings
from usage_monitor.services.settings.store import SettingsStore
from usage_monitor.services.state_store import StateStore
from usage_monitor.services.update_check import UpdateChecker, UpdateState
from usage_monitor.ui import theme
from usage_monitor.ui.bridge import Bridge
from usage_monitor.ui.hovercard import HoverCard
from usage_monitor.ui.settings_dialog.dialog import SettingsDialog
from usage_monitor.ui.theme import DialogPalette, Palette
from usage_monitor.ui.tray.tray import Tray
from usage_monitor.ui.viewmodel import (
    AuthNotifier,
    ColumnVM,
    ProviderInfo,
    build_tray_vm,
    build_widget_vm,
    update_menu_text,
)
from usage_monitor.ui.widget import menu, placement
from usage_monitor.ui.widget.widget import UsageWidget

log = logging.getLogger(__name__)

HOTKEY_ID = 0x5531


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback: Callable[[], None]) -> None:
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - Qt 的介面
        if event_type == b"windows_generic_MSG" and hotkey.is_hotkey_message(
            int(message), HOTKEY_ID
        ):
            QTimer.singleShot(0, self._callback)
            return True, 0
        return False, 0


def system_ui_languages() -> list[str]:
    """Windows 顯示語言（例如 ["zh-Hant-TW", "zh-TW", …]）；獨立成函式，測試可以固定它。"""
    return list(QLocale.system().uiLanguages())


def resolve_palette(choice: str, scheme: Qt.ColorScheme) -> Palette:
    if choice == "light":
        return theme.LIGHT
    if choice == "dark":
        return theme.DARK
    return theme.LIGHT if scheme == Qt.ColorScheme.Light else theme.DARK


def screen_infos() -> list[placement.ScreenInfo]:
    primary = QGuiApplication.primaryScreen()
    result: list[placement.ScreenInfo] = []
    for s in QGuiApplication.screens():
        g = s.availableGeometry()
        result.append(
            placement.ScreenInfo(
                s.name(), placement.Rect(g.x(), g.y(), g.width(), g.height()), s is primary
            )
        )
    return result


class Controller(QObject):
    def __init__(
        self,
        app: QApplication,
        settings_store: SettingsStore,
        states: StateStore,
        catalog: Sequence[ProviderInfo],
        clock: Clock,
        *,
        refresh: Callable[[], None],
        log_file: Path,
        on_quit: Callable[[], None],
        settings_file: Path | None = None,
        updates: UpdateChecker | None = None,
    ) -> None:
        """`catalog`：所有可用的服務；實際顯示哪些依設定的 providers 決定。"""
        super().__init__()
        self._app = app
        self._store = settings_store
        self._settings: Settings = settings_store.current
        self._states = states
        self._catalog = list(catalog)
        self._providers = self._enabled_providers(self._settings)
        self._settings_file = settings_file or settings_store.path
        self._dialog: SettingsDialog | None = None
        self._updates = updates
        self._on_notification_click: Callable[[], None] = launch.run_diagnose
        """點通知要做什麼：認證錯誤 → 執行診斷；新版本 → 開 Release 頁面。"""
        self._clock = clock
        self._refresh = refresh
        self._log_file = log_file
        self._on_quit = on_quit
        self._fs_active = False
        self._fs_suppressed = False
        """使用者在全螢幕時手動叫出小工具：這次全螢幕結束前不再自動隱藏。"""
        self._hotkey_registered = False
        self._notifier = AuthNotifier()
        self._lang = self._resolve_lang(self._settings)

        palette = self._palette()
        self.widget = UsageWidget(self._widget_vm(), palette, self.opacity)
        self.card = HoverCard(palette)
        self.card.set_lang(self._lang)
        self.widget_menu = menu.build_widget_menu(self)
        self.tray = Tray(self._tray_vm(), menu.build_tray_menu(self))

        self._bridge = Bridge(states, settings_store, updates)
        self._bridge.update_changed.connect(self._on_update)
        self._bridge.state_changed.connect(self._on_state)
        self._bridge.settings_changed.connect(self._on_settings)

        self.widget.refresh_requested.connect(self.refresh)
        self.widget.menu_requested.connect(self._show_widget_menu)
        self.widget.drag_finished.connect(self._on_drag_finished)
        self.widget.hover_column.connect(self._on_hover)
        self.tray.toggle_requested.connect(self.toggle_widget)
        self.tray.notification_clicked.connect(lambda: self._on_notification_click())

        hints = QGuiApplication.styleHints()
        hints.colorSchemeChanged.connect(lambda _scheme: self._apply_palette())

        self._repaint = QTimer(self)
        self._repaint.setInterval(theme.REPAINT_MS)
        self._repaint.timeout.connect(self._render)
        self._housekeeping = QTimer(self)
        self._housekeeping.setInterval(theme.HOUSEKEEPING_MS)
        self._housekeeping.timeout.connect(self._on_housekeeping)

        self._hotkey_filter = _HotkeyFilter(self.toggle_widget)
        app.installNativeEventFilter(self._hotkey_filter)

        app.screenAdded.connect(self._on_screens_changed)
        app.screenRemoved.connect(self._on_screens_changed)
        app.primaryScreenChanged.connect(self._on_screens_changed)
        for screen in app.screens():
            self._watch_screen(screen)

    # ---------------------------------------------------------------- 啟動／結束

    def start(self) -> None:
        self.tray.show()
        self._place()
        self._register_hotkey()
        self._apply_visibility()
        self._repaint.start()
        self._housekeeping.start()

    def shutdown(self) -> None:
        self._repaint.stop()
        self._housekeeping.stop()
        if self._hotkey_registered:
            hotkey.unregister(self.widget.hwnd, HOTKEY_ID)
        self._bridge.close()
        if self._dialog is not None:
            self._dialog.hide()
        self.card.hide()
        self.tray.hide()
        self.widget.hide()

    # ---------------------------------------------------------------- MenuHost

    @property
    def locked(self) -> bool:
        return self._settings.widget.locked

    @property
    def opacity(self) -> float:
        return self._settings.widget.opacity

    @property
    def widget_visible(self) -> bool:
        return self._settings.widget.visible

    @property
    def autostart_enabled(self) -> bool:
        return autostart.is_enabled()

    @property
    def hotkey(self) -> str:
        return self._settings.widget.hotkey

    def refresh(self) -> None:
        self._refresh()

    def set_locked(self, locked: bool) -> None:
        self._update_widget_settings(locked=locked)

    def set_opacity(self, opacity: float) -> None:
        self._update_widget_settings(opacity=opacity)

    def reset_position(self) -> None:
        self._update_widget_settings(screen=None, pos=None)
        self._place()

    def set_widget_visible(self, visible: bool) -> None:
        if visible and self._fs_active:
            self._fs_suppressed = True
        self._update_widget_settings(visible=visible)

    def toggle_widget(self) -> None:
        self.set_widget_visible(not self.widget.isVisible())

    def set_autostart(self, enabled: bool) -> None:
        try:
            autostart.set_enabled(enabled)
        except OSError as e:
            log.warning("無法變更開機啟動：%s", e)
        if self._dialog is not None:
            self._dialog.refresh()

    def provider_enabled(self, provider_id: str) -> bool:
        return provider_id in self._settings.providers

    def set_provider_enabled(self, provider_id: str, enabled: bool) -> None:
        """開關一個 AI 監控對象（右鍵選單與設定視窗共用）；順序依 catalog，未知的服務保留在後面。"""

        def change(s: Settings) -> Settings:
            current = set(s.providers)
            wanted = current | {provider_id} if enabled else current - {provider_id}
            known = [pid for pid, _ in self._catalog]
            ordered = [pid for pid in known if pid in wanted]
            ordered += [pid for pid in s.providers if pid in wanted and pid not in known]
            return replace(s, providers=tuple(ordered))

        self.update_settings(change)

    def open_settings(self) -> None:
        if self._dialog is None:
            self._dialog = SettingsDialog(self)
        self._dialog.show_and_raise()

    def open_log(self) -> None:
        launch.open_path(self._log_file)

    # ---------------------------------------------------------------- SettingsHost

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def catalog(self) -> Sequence[ProviderInfo]:
        return self._catalog

    @property
    def hotkey_registered(self) -> bool:
        return self._hotkey_registered

    @property
    def settings_file(self) -> Path:
        return self._settings_file

    @property
    def log_file(self) -> Path:
        return self._log_file

    def update_settings(self, change: Callable[[Settings], Settings]) -> None:
        try:
            self._store.update(change)
        except OSError as e:
            log.warning("設定寫不進去（%s），只在這次執行中生效", type(e).__name__)
            self._on_settings(change(self._settings))

    def provider_state(self, provider_id: str) -> ProviderState | None:
        return self._states.get(provider_id)

    def now(self) -> datetime:
        return self._clock.now()

    @property
    def lang(self) -> Lang:
        return self._lang

    def dialog_palette(self) -> DialogPalette:
        return theme.DIALOG_LIGHT if self._palette() is theme.LIGHT else theme.DIALOG_DARK

    def open_log_folder(self) -> None:
        launch.open_path(self._log_file.parent)

    def run_diagnose(self) -> None:
        launch.run_diagnose()

    # ---------------------------------------------------------------- 更新檢查

    @property
    def update_state(self) -> UpdateState | None:
        return self._updates.state if self._updates is not None else None

    @property
    def update_menu_label(self) -> str | None:
        return update_menu_text(self.update_state, self._lang)

    def check_updates_now(self) -> None:
        if self._updates is not None:
            self._updates.check_now()

    def open_release_page(self) -> None:
        state = self.update_state
        launch.open_url(state.url if state is not None else app_info.RELEASES_URL)

    def skip_update(self) -> None:
        if self._updates is not None:
            self._updates.skip_latest()

    def open_url(self, url: str) -> None:
        launch.open_url(url)

    def _on_update(self, _state: object) -> None:
        self._render()
        if self._dialog is not None:
            self._dialog.refresh_update()
        version = self._updates.claim_notification() if self._updates is not None else None
        if version is not None:
            self._on_notification_click = self.open_release_page
            self.tray.notify(
                t(self._lang, "notify_update_title", version=version),
                t(self._lang, "notify_update_body"),
            )

    def quit(self) -> None:
        self._on_quit()

    # ---------------------------------------------------------------- 設定

    def _update_widget_settings(self, **changes: object) -> None:
        def change(s: Settings) -> Settings:
            return replace(s, widget=replace(s.widget, **changes))  # type: ignore[arg-type]

        self.update_settings(change)

    @staticmethod
    def _resolve_lang(settings: Settings) -> Lang:
        return resolve_language(settings.language, system_ui_languages())

    def _apply_language(self, lang: Lang) -> None:
        """切換語言：重建選單與設定視窗（設定視窗開著就重新開在原本的頁面）。"""
        self._lang = lang
        self.card.set_lang(lang)
        self.widget_menu = menu.build_widget_menu(self)
        self.tray.set_menu(menu.build_tray_menu(self))
        if self._dialog is not None:
            was_visible = self._dialog.isVisible()
            page = self._dialog.nav.currentRow()
            geometry = self._dialog.geometry()
            self._dialog.hide()
            self._dialog.deleteLater()
            self._dialog = SettingsDialog(self)
            self._dialog.nav.setCurrentRow(page)
            self._dialog.setGeometry(geometry)
            if was_visible:
                self._dialog.show()

    def _enabled_providers(self, settings: Settings) -> list[ProviderInfo]:
        """依設定的順序；設定裡有、但目前程式不認得的服務略過。"""
        names = dict(self._catalog)
        return [(pid, names[pid]) for pid in settings.providers if pid in names]

    def _on_settings(self, settings: Settings) -> None:
        old: WidgetSettings = self._settings.widget
        self._settings = settings
        new = settings.widget
        self._providers = self._enabled_providers(settings)
        if new.opacity != old.opacity:
            self.widget.set_opacity(new.opacity)
        if new.theme != old.theme:
            self._apply_palette()
        lang = self._resolve_lang(settings)
        if lang is not self._lang:
            self._apply_language(lang)
        if new.hotkey != old.hotkey:
            self._register_hotkey()
        self._render()
        self._apply_visibility()
        if self._updates is not None:
            self._updates.settings_changed()
        if self._dialog is not None:
            self._dialog.refresh()

    # ---------------------------------------------------------------- 重畫

    def _widget_vm(self):
        return build_widget_vm(
            self._providers,
            self._states.all(),
            self._clock.now(),
            locked=self.locked,
            lang=self._lang,
        )

    def _tray_vm(self):
        return build_tray_vm(
            self._providers,
            self._states.all(),
            self._clock.now(),
            lang=self._lang,
            update_available=self.update_state is not None and self.update_state.should_alert,
        )

    def _render(self) -> None:
        self.widget.set_vm(self._widget_vm())
        self.tray.set_vm(self._tray_vm())

    def _on_state(self, _state: ProviderState) -> None:
        self._render()
        for n in self._notifier.update(self._providers, self._states.all(), self._lang):
            self._on_notification_click = launch.run_diagnose
            self.tray.notify(n.title, f"{n.body}\n{t(self._lang, 'notify_click')}")
        if self._dialog is not None and self._dialog.isVisible():
            self._dialog.refresh_services()

    def _palette(self) -> Palette:
        return resolve_palette(
            self._settings.widget.theme, QGuiApplication.styleHints().colorScheme()
        )

    def _apply_palette(self) -> None:
        palette = self._palette()
        self.widget.set_palette(palette)
        self.card.set_palette(palette)
        if self._dialog is not None:
            self._dialog.apply_palette(self.dialog_palette())

    # ---------------------------------------------------------------- 顯示／隱藏

    def _apply_visibility(self) -> None:
        hidden_by_fs = (
            self._settings.widget.hide_on_fullscreen and self._fs_active and not self._fs_suppressed
        )
        visible = self._settings.widget.visible and not hidden_by_fs
        if visible and not self.widget.isVisible():
            self.widget.show()
        elif not visible and self.widget.isVisible():
            self.card.hide()
            self.widget.hide()

    def _on_housekeeping(self) -> None:
        fs = (
            fullscreen.is_foreground_fullscreen()
            if self._settings.widget.hide_on_fullscreen
            else False
        )
        if fs != self._fs_active:
            self._fs_active = fs
            if not fs:
                self._fs_suppressed = False
            self._apply_visibility()
        # 右鍵選單（小工具或系統匣）開著時不重設：否則小工具會被抬到選單上面、把選單蓋住
        if self.widget.isVisible() and QApplication.activePopupWidget() is None:
            topmost.reassert_topmost(self.widget.hwnd)

    def _register_hotkey(self) -> None:
        hwnd = self.widget.hwnd
        if self._hotkey_registered:
            hotkey.unregister(hwnd, HOTKEY_ID)
        self._hotkey_registered = hotkey.register(hwnd, HOTKEY_ID, self._settings.widget.hotkey)

    # ---------------------------------------------------------------- 選單、懸停

    def _show_widget_menu(self, pos: QPoint) -> None:
        self.card.hide()
        self.widget_menu.popup(pos)

    def _on_hover(self, column: ColumnVM | None, anchor: QRect) -> None:
        if column is None:
            self.card.hide()
            return
        screen = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
        self.card.show_for(column.hover, anchor, screen.availableGeometry())

    # ---------------------------------------------------------------- 位置

    def _size(self) -> placement.Size:
        return self.widget.width(), self.widget.height()

    def _place(self) -> None:
        w = self._settings.widget
        x, y = placement.restore(w.screen, w.pos, self._size(), screen_infos())
        self.widget.move(QPoint(x, y))

    def _on_drag_finished(self) -> None:
        screens = screen_infos()
        pos = (self.widget.x(), self.widget.y())
        screen = placement.screen_for(pos, self._size(), screens)
        snapped = placement.snap(pos, self._size(), screen.work)
        self.widget.move(QPoint(*snapped))
        name, rel = placement.to_saved(snapped, self._size(), screens)
        self._update_widget_settings(screen=name, pos=rel)

    def _watch_screen(self, screen: QScreen) -> None:
        screen.availableGeometryChanged.connect(lambda _g: self._on_screens_changed())

    def _on_screens_changed(self, screen: QScreen | None = None) -> None:
        if isinstance(screen, QScreen):
            self._watch_screen(screen)
        # 螢幕設定剛變動時幾何資訊可能還沒穩定，稍等再重新放置
        QTimer.singleShot(500, self._place)
