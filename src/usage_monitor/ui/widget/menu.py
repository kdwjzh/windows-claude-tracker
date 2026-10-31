"""小工具與系統匣的右鍵選單（設計稿畫板 3-B、4）。

選單項目的狀態（打勾）在每次打開前從 MenuHost 重新讀取；文字依 host.lang，
切換語言時 controller 會重建選單。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu

from usage_monitor.core.i18n import Lang, t
from usage_monitor.ui import theme


class MenuHost(Protocol):
    @property
    def lang(self) -> Lang: ...
    @property
    def locked(self) -> bool: ...
    @property
    def opacity(self) -> float: ...
    @property
    def widget_visible(self) -> bool: ...
    @property
    def autostart_enabled(self) -> bool: ...
    @property
    def hotkey(self) -> str: ...
    @property
    def update_menu_label(self) -> str | None:
        """有新版本時系統匣選單最上面那一行；沒有則 None。"""
        ...

    def refresh(self) -> None: ...
    def open_release_page(self) -> None: ...
    def set_locked(self, locked: bool) -> None: ...
    def set_opacity(self, opacity: float) -> None: ...
    def reset_position(self) -> None: ...
    def set_widget_visible(self, visible: bool) -> None: ...
    def set_autostart(self, enabled: bool) -> None: ...
    def open_settings(self) -> None: ...
    def open_log(self) -> None: ...
    def quit(self) -> None: ...


def _action(
    menu: QMenu,
    text: str,
    slot: Callable[[], None],
    *,
    shortcut_hint: str | None = None,
) -> QAction:
    label = f"{text}\t{shortcut_hint}" if shortcut_hint else text
    action = menu.addAction(label)
    action.triggered.connect(slot)
    return action


def _check(menu: QMenu, text: str, slot: Callable[[bool], None]) -> QAction:
    action = menu.addAction(text)
    action.setCheckable(True)
    action.triggered.connect(slot)
    return action


def build_widget_menu(host: MenuHost) -> QMenu:
    lang = host.lang
    menu = QMenu()
    _action(menu, t(lang, "menu_refresh"), host.refresh, shortcut_hint=t(lang, "menu_double_click"))
    menu.addSeparator()
    lock = _check(menu, t(lang, "menu_lock"), host.set_locked)

    opacity_menu = menu.addMenu(t(lang, "menu_opacity"))
    group = QActionGroup(opacity_menu)
    opacity_actions: list[tuple[float, QAction]] = []
    for value in theme.OPACITY_CHOICES:
        a = opacity_menu.addAction(f"{round(value * 100)}%")
        a.setCheckable(True)
        group.addAction(a)
        a.triggered.connect(lambda _=False, v=value: host.set_opacity(v))
        opacity_actions.append((value, a))

    _action(menu, t(lang, "menu_reset_position"), host.reset_position)
    menu.addSeparator()
    hide = _action(menu, t(lang, "menu_hide"), lambda: host.set_widget_visible(False))
    _action(menu, t(lang, "menu_settings"), host.open_settings)
    _action(menu, t(lang, "menu_open_log"), host.open_log)
    menu.addSeparator()
    _action(menu, t(lang, "menu_quit"), host.quit)

    def refresh_state() -> None:
        lock.setChecked(host.locked)
        hide.setText(f"{t(lang, 'menu_hide')}\t{host.hotkey}")
        for value, a in opacity_actions:
            a.setChecked(abs(value - host.opacity) < 0.01)

    menu.aboutToShow.connect(refresh_state)
    refresh_state()
    return menu


def build_tray_menu(host: MenuHost) -> QMenu:
    lang = host.lang
    menu = QMenu()
    update = _action(menu, "", host.open_release_page)
    update_separator = menu.addSeparator()
    visible = _check(menu, t(lang, "menu_show"), host.set_widget_visible)
    _action(menu, t(lang, "menu_refresh"), host.refresh)
    menu.addSeparator()
    lock = _check(menu, t(lang, "menu_lock"), host.set_locked)
    _action(menu, t(lang, "menu_reset_position"), host.reset_position)
    menu.addSeparator()
    autostart = _check(menu, t(lang, "menu_autostart"), host.set_autostart)
    _action(menu, t(lang, "menu_settings"), host.open_settings)
    _action(menu, t(lang, "menu_open_log"), host.open_log)
    menu.addSeparator()
    _action(menu, t(lang, "menu_quit"), host.quit)

    def refresh_state() -> None:
        label = host.update_menu_label
        update.setText(label or "")
        update.setVisible(label is not None)
        update_separator.setVisible(label is not None)
        visible.setChecked(host.widget_visible)
        lock.setChecked(host.locked)
        autostart.setChecked(host.autostart_enabled)

    menu.aboutToShow.connect(refresh_state)
    refresh_state()
    return menu
