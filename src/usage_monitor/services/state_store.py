"""保存各服務最新的 ProviderState；變更時通知訂閱者（UI 透過 bridge 轉回主執行緒）。"""

from __future__ import annotations

import threading
from collections.abc import Callable

from usage_monitor.core.models import ProviderState
from usage_monitor.services.subscribers import Subscribers


class StateStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, ProviderState] = {}
        self._subscribers: Subscribers[ProviderState] = Subscribers()

    def update(self, state: ProviderState) -> None:
        with self._lock:
            self._states[state.provider_id] = state
        self._subscribers.notify(state)

    def get(self, provider_id: str) -> ProviderState | None:
        with self._lock:
            return self._states.get(provider_id)

    def all(self) -> dict[str, ProviderState]:
        with self._lock:
            return dict(self._states)

    def remove(self, provider_id: str) -> None:
        """服務停用時移除；不通知（UI 會依設定重建欄位）。"""
        with self._lock:
            self._states.pop(provider_id, None)

    def subscribe(self, callback: Callable[[ProviderState], None]) -> Callable[[], None]:
        return self._subscribers.add(callback)
