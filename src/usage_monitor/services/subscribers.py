"""簡單的訂閱者清單：通知時一個訂閱者出錯不會影響其他訂閱者。"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Generic, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


class Subscribers(Generic[T]):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[T], None]] = []

    def add(self, callback: Callable[[T], None]) -> Callable[[], None]:
        """加入訂閱者；回傳取消訂閱的函式。"""
        with self._lock:
            self._callbacks.append(callback)

        def remove() -> None:
            with self._lock:
                if callback in self._callbacks:
                    self._callbacks.remove(callback)

        return remove

    def notify(self, value: T) -> None:
        """在呼叫端的執行緒上依序呼叫訂閱者（UI 端要自己轉回主執行緒）。"""
        with self._lock:
            callbacks = list(self._callbacks)
        for callback in callbacks:
            try:
                callback(value)
            except Exception:
                log.exception("訂閱者處理通知時發生錯誤")
