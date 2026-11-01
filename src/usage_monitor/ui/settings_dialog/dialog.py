"""設定視窗（設計稿畫板 5）：左側導覽「一般／進階／關於」，改了立即生效、不需要「儲存」。

只透過 SettingsHost 讀寫設定與查詢狀態；外部（右鍵選單、快捷鍵）改了設定時，
controller 會呼叫 refresh() 把畫面同步回來。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from usage_monitor import __version__
from usage_monitor.core import app_info
from usage_monitor.core.i18n import LANGUAGE_CHOICES, LANGUAGE_NAMES, Lang, t
from usage_monitor.core.models import ProviderState
from usage_monitor.services.settings.schema import MIN_OPACITY, Settings, WidgetSettings
from usage_monitor.services.update_check import UpdateState, UpdateStatus
from usage_monitor.ui import theme
from usage_monitor.ui.settings_dialog.style import stylesheet
from usage_monitor.ui.settings_dialog.widgets import (
    HotkeyButton,
    LabeledSwitch,
    SettingCard,
    section_label,
)
from usage_monitor.ui.theme import DialogPalette
from usage_monitor.ui.viewmodel import (
    ProviderInfo,
    StatusKind,
    service_status,
    update_status_text,
)

THEME_CHOICES = (("system", "theme_system"), ("dark", "theme_dark"), ("light", "theme_light"))
"""(設定值, 翻譯 key)"""
OPACITY_DEBOUNCE_MS = 150


class SettingsHost(Protocol):
    @property
    def lang(self) -> Lang: ...
    @property
    def settings(self) -> Settings: ...
    @property
    def catalog(self) -> Sequence[ProviderInfo]: ...
    @property
    def autostart_enabled(self) -> bool: ...
    @property
    def hotkey_registered(self) -> bool: ...
    @property
    def settings_file(self) -> Path: ...
    @property
    def log_file(self) -> Path: ...

    def update_settings(self, change: Callable[[Settings], Settings]) -> None: ...
    def set_autostart(self, enabled: bool) -> None: ...
    def set_provider_enabled(self, provider_id: str, enabled: bool) -> None: ...
    def provider_state(self, provider_id: str) -> ProviderState | None: ...
    def now(self) -> datetime: ...
    def dialog_palette(self) -> DialogPalette: ...
    def open_log_folder(self) -> None: ...
    def run_diagnose(self) -> None: ...
    @property
    def update_state(self) -> UpdateState | None: ...
    def check_updates_now(self) -> None: ...
    def open_release_page(self) -> None: ...
    def skip_update(self) -> None: ...
    def open_url(self, url: str) -> None: ...


def _page(title: str) -> tuple[QScrollArea, QVBoxLayout]:
    content = QWidget()
    content.setObjectName("page")
    lay = QVBoxLayout(content)
    lay.setContentsMargins(28, 20, 28, 28)
    lay.setSpacing(6)
    heading = QLabel(title)
    heading.setObjectName("pageTitle")
    lay.addWidget(heading)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(content)
    return scroll, lay


class SettingsDialog(QWidget):
    def __init__(self, host: SettingsHost) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("settingsRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._host = host
        self._lang = host.lang
        self.setWindowTitle(t(self._lang, "settings_title"))
        self.resize(780, 680)
        self.setMinimumSize(640, 480)
        self._palette = host.dialog_palette()
        self._switches: list[LabeledSwitch] = []

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(190)
        self.nav.addItems([t(self._lang, k) for k in ("nav_general", "nav_advanced", "nav_about")])
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_general())
        self.pages.addWidget(self._build_advanced())
        self.pages.addWidget(self._build_about())
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 16, 0, 0)
        root.setSpacing(8)
        root.addWidget(self.nav)
        root.addWidget(self.pages, 1)

        self._opacity_timer = QTimer(self)
        self._opacity_timer.setSingleShot(True)
        self._opacity_timer.setInterval(OPACITY_DEBOUNCE_MS)
        self._opacity_timer.timeout.connect(self._commit_opacity)

        self.apply_palette(self._palette)
        self.refresh()

    # ---------------------------------------------------------------- 建立頁面

    def _switch(self, on_toggle: Callable[[bool], None]) -> LabeledSwitch:
        s = LabeledSwitch(self._palette, self._lang)
        s.toggled.connect(on_toggle)
        self._switches.append(s)
        return s

    def _build_general(self) -> QWidget:
        lang = self._lang
        page, lay = _page(t(lang, "nav_general"))

        lay.addWidget(section_label(t(lang, "section_update")))
        self.interval = QComboBox()
        self.interval.currentIndexChanged.connect(self._on_interval)
        lay.addWidget(SettingCard(t(lang, "interval"), self.interval, t(lang, "interval_hint")))
        self.autostart = self._switch(self._host.set_autostart)
        lay.addWidget(SettingCard(t(lang, "autostart"), self.autostart))

        lay.addWidget(section_label(t(lang, "section_widget")))
        self.visible = self._switch(lambda v: self._widget(visible=v))
        lay.addWidget(SettingCard(t(lang, "visible"), self.visible))
        self.locked = self._switch(lambda v: self._widget(locked=v))
        lay.addWidget(SettingCard(t(lang, "locked"), self.locked, t(lang, "locked_hint")))

        opacity_box = QWidget()
        ol = QHBoxLayout(opacity_box)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(14)
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(round(MIN_OPACITY * 100), 100)
        self.opacity.setSingleStep(5)
        self.opacity.setPageStep(10)
        self.opacity.setFixedWidth(180)
        self.opacity_value = QLabel()
        self.opacity_value.setObjectName("valueLabel")
        self.opacity_value.setFixedWidth(44)
        ol.addWidget(self.opacity)
        ol.addWidget(self.opacity_value)
        self.opacity.valueChanged.connect(self._on_opacity)
        lay.addWidget(SettingCard(t(lang, "opacity"), opacity_box))

        self.fullscreen = self._switch(lambda v: self._widget(hide_on_fullscreen=v))
        lay.addWidget(
            SettingCard(t(lang, "fullscreen"), self.fullscreen, t(lang, "fullscreen_hint"))
        )

        hotkey_box = QWidget()
        hl = QHBoxLayout(hotkey_box)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        self.hotkey_label = QLabel()
        self.hotkey_label.setObjectName("hotkeyBox")
        self.hotkey_button = HotkeyButton(lang)
        self.hotkey_button.captured.connect(lambda text: self._widget(hotkey=text))
        hl.addWidget(self.hotkey_label)
        hl.addWidget(self.hotkey_button)
        self.hotkey_card = SettingCard(t(lang, "hotkey"), hotkey_box)
        lay.addWidget(self.hotkey_card)

        self.theme = QComboBox()
        for _, key in THEME_CHOICES:
            self.theme.addItem(t(lang, key))
        self.theme.currentIndexChanged.connect(
            lambda i: self._widget(theme=THEME_CHOICES[i][0]) if i >= 0 else None
        )
        lay.addWidget(SettingCard(t(lang, "theme"), self.theme))

        self.language = QComboBox()
        for value in LANGUAGE_CHOICES:
            label = t(lang, "language_system") if value == "system" else LANGUAGE_NAMES[Lang(value)]
            self.language.addItem(label, value)
        self.language.currentIndexChanged.connect(self._on_language)
        lay.addWidget(SettingCard(t(lang, "language"), self.language))

        lay.addWidget(section_label(t(lang, "section_services")))
        self.service_cards: dict[str, tuple[SettingCard, LabeledSwitch]] = {}
        for pid, name in self._host.catalog:
            switch = self._switch(lambda v, pid=pid: self._set_service(pid, v))
            card = SettingCard(name, switch, " ")
            self.service_cards[pid] = (card, switch)
            lay.addWidget(card)
        lay.addStretch(1)
        return page

    def _build_advanced(self) -> QWidget:
        lang = self._lang
        page, lay = _page(t(lang, "nav_advanced"))
        self.cli_refresh = self._switch(lambda v: self._update(allow_cli_refresh=v))
        lay.addWidget(
            SettingCard(
                t(lang, "cli_refresh"),
                self.cli_refresh,
                t(lang, "cli_refresh_hint"),
            )
        )
        open_logs = QPushButton(t(lang, "open"))
        open_logs.clicked.connect(self._host.open_log_folder)
        lay.addWidget(SettingCard(t(lang, "open_logs"), open_logs, t(lang, "open_logs_hint")))
        diagnose = QPushButton(t(lang, "run"))
        diagnose.clicked.connect(self._host.run_diagnose)
        lay.addWidget(SettingCard(t(lang, "diagnose"), diagnose, t(lang, "diagnose_hint")))
        lay.addStretch(1)
        return page

    def _build_about(self) -> QWidget:
        """關於（CLAUDE.md §3.7）：版本＋檢查更新、自動檢查、略過版本、專案網址、授權、免責聲明。"""
        lang = self._lang
        page, lay = _page(t(lang, "nav_about"))

        lay.addWidget(section_label(t(lang, "section_version")))
        buttons = QWidget()
        bl = QHBoxLayout(buttons)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        self.update_download = QPushButton(t(lang, "update_download"))
        self.update_download.clicked.connect(self._host.open_release_page)
        self.update_check = QPushButton(f"⟳  {t(lang, 'update_check_now')}")
        self.update_check.clicked.connect(self._host.check_updates_now)
        bl.addWidget(self.update_download)
        bl.addWidget(self.update_check)
        self.version_card = SettingCard(t(lang, "about_app", version=__version__), buttons, " ")
        lay.addWidget(self.version_card)

        self.update_auto = self._switch(
            lambda v: self._host.update_settings(
                lambda s: replace(s, update_check=replace(s.update_check, enabled=v))
            )
        )
        lay.addWidget(
            SettingCard(t(lang, "update_auto"), self.update_auto, t(lang, "update_auto_hint"))
        )
        self.update_skip = QPushButton(t(lang, "update_skip"))
        self.update_skip.clicked.connect(self._host.skip_update)
        self.skip_card = SettingCard(
            t(lang, "update_skip"), self.update_skip, t(lang, "update_skip_hint")
        )
        lay.addWidget(self.skip_card)

        lay.addWidget(section_label(t(lang, "section_project")))
        open_project = QPushButton(t(lang, "open"))
        open_project.clicked.connect(lambda: self._host.open_url(app_info.REPO_URL))
        lay.addWidget(SettingCard(t(lang, "about_project"), open_project, app_info.REPO_URL))
        lay.addWidget(SettingCard(t(lang, "about_license"), None, t(lang, "about_license_value")))
        self.settings_path = SettingCard(
            t(lang, "about_settings_file"), None, str(self._host.settings_file)
        )
        lay.addWidget(self.settings_path)
        lay.addWidget(SettingCard(t(lang, "about_log_file"), None, str(self._host.log_file)))
        self.disclaimer = QLabel(t(lang, "about_disclaimer"))
        self.disclaimer.setObjectName("cardSubtitle")
        self.disclaimer.setWordWrap(True)
        lay.addWidget(self.disclaimer)
        lay.addStretch(1)
        return page

    def refresh_update(self) -> None:
        """依 UpdateState 更新「關於」頁（背景檢查完成時 controller 會呼叫）。"""
        state = self._host.update_state
        name = (
            "statusOk"
            if state is not None and (state.should_alert or state.status is UpdateStatus.UP_TO_DATE)
            else "cardSubtitle"
        )
        self.version_card.set_subtitle(update_status_text(state, self._lang), name)
        alert = state is not None and state.should_alert
        self.update_download.setVisible(alert)
        self.update_skip.setEnabled(alert)
        self.skip_card.setVisible(alert)
        self.update_check.setEnabled(state is None or state.status is not UpdateStatus.CHECKING)
        self.update_auto.set_checked_silently(self._host.settings.update_check.enabled)

    # ---------------------------------------------------------------- 寫入設定

    def _update(self, **changes: object) -> None:
        self._host.update_settings(lambda s: replace(s, **changes))  # type: ignore[arg-type]

    def _widget(self, **changes: object) -> None:
        def change(s: Settings) -> Settings:
            widget: WidgetSettings = replace(s.widget, **changes)  # type: ignore[arg-type]
            return replace(s, widget=widget)

        self._host.update_settings(change)

    def _on_interval(self, index: int) -> None:
        minutes = self.interval.itemData(index)
        if isinstance(minutes, int) and minutes != self._host.settings.interval_minutes:
            self._update(interval_minutes=minutes)

    def _on_opacity(self, value: int) -> None:
        self.opacity_value.setText(f"{value}%")
        self._opacity_timer.start()

    def _commit_opacity(self) -> None:
        value = round(self.opacity.value() / 100, 2)
        if abs(value - self._host.settings.widget.opacity) > 1e-6:
            self._widget(opacity=value)

    def _on_language(self, index: int) -> None:
        value = self.language.itemData(index)
        if isinstance(value, str) and value != self._host.settings.language:
            self._update(language=value)

    def _set_service(self, provider_id: str, enabled: bool) -> None:
        self._host.set_provider_enabled(provider_id, enabled)

    # ---------------------------------------------------------------- 同步畫面

    def refresh(self) -> None:
        """依目前設定與狀態更新所有控制項（不觸發寫入）。"""
        s = self._host.settings
        w = s.widget

        self.interval.blockSignals(True)
        self.interval.clear()
        choices = sorted({*theme.INTERVAL_CHOICES, s.interval_minutes})
        for minutes in choices:
            self.interval.addItem(t(self._lang, "interval_choice", n=minutes), minutes)
        self.interval.setCurrentIndex(choices.index(s.interval_minutes))
        self.interval.blockSignals(False)

        self.autostart.set_checked_silently(self._host.autostart_enabled)
        self.visible.set_checked_silently(w.visible)
        self.locked.set_checked_silently(w.locked)
        self.fullscreen.set_checked_silently(w.hide_on_fullscreen)
        self.cli_refresh.set_checked_silently(s.allow_cli_refresh)

        if not self._opacity_timer.isActive():
            self.opacity.blockSignals(True)
            self.opacity.setValue(round(w.opacity * 100))
            self.opacity.blockSignals(False)
            self.opacity_value.setText(f"{round(w.opacity * 100)}%")

        self.hotkey_label.setText(w.hotkey.replace("+", " + "))
        if self._host.hotkey_registered:
            self.hotkey_card.set_subtitle("")
        else:
            self.hotkey_card.set_subtitle(t(self._lang, "hotkey_failed"), "statusError")

        self.theme.blockSignals(True)
        ids = [value for value, _ in THEME_CHOICES]
        self.theme.setCurrentIndex(ids.index(w.theme) if w.theme in ids else 0)
        self.theme.blockSignals(False)

        self.language.blockSignals(True)
        index = self.language.findData(s.language)
        self.language.setCurrentIndex(max(index, 0))
        self.language.blockSignals(False)

        self.refresh_services()
        self.refresh_update()

    def refresh_services(self) -> None:
        enabled = set(self._host.settings.providers)
        now = self._host.now()
        for pid, (card, switch) in self.service_cards.items():
            switch.set_checked_silently(pid in enabled)
            status = service_status(
                pid in enabled, self._host.provider_state(pid), now, self._lang, card.title.text()
            )
            name = {StatusKind.OK: "statusOk", StatusKind.ERROR: "statusError"}.get(
                status.kind, "cardSubtitle"
            )
            card.set_subtitle(status.text, name)

    def apply_palette(self, palette: DialogPalette) -> None:
        self._palette = palette
        self.setStyleSheet(stylesheet(palette, self._lang))
        for s in self._switches:
            s.set_palette(palette)

    # ---------------------------------------------------------------- 視窗

    def show_and_raise(self) -> None:
        self.refresh()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt 的命名
        """關閉只是隱藏；下次開啟沿用同一個視窗。"""
        if self._opacity_timer.isActive():
            self._opacity_timer.stop()
            self._commit_opacity()
        event.ignore()
        self.hide()
