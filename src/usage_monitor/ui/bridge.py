"""把 services 的回呼（可能在背景執行緒）轉成 Qt Signal，送回主執行緒（CLAUDE.md §5.2 第 13 條）。

Bridge 物件住在主執行緒；從其他執行緒 emit 時 Qt 會自動改用 queued connection。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from usage_monitor.core.models import ProviderState
from usage_monitor.services.settings.schema import Settings
from usage_monitor.services.settings.store import SettingsStore
from usage_monitor.services.state_store import StateStore
from usage_monitor.services.update_check import UpdateChecker


class Bridge(QObject):
    state_changed = Signal(object)
    """ProviderState"""
    settings_changed = Signal(object)
    """Settings"""
    update_changed = Signal(object)
    """UpdateState"""

    def __init__(
        self,
        states: StateStore,
        settings: SettingsStore,
        updates: UpdateChecker | None = None,
    ) -> None:
        super().__init__()
        self._unsubscribe: list[Callable[[], None]] = [
            states.subscribe(self._emit_state),
            settings.subscribe(self._emit_settings),
        ]
        if updates is not None:
            self._unsubscribe.append(updates.subscribe(self.update_changed.emit))

    def _emit_state(self, state: ProviderState) -> None:
        self.state_changed.emit(state)

    def _emit_settings(self, settings: Settings) -> None:
        self.settings_changed.emit(settings)

    def close(self) -> None:
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe.clear()
