"""單一執行個體：Named mutex。"""

from __future__ import annotations

import ctypes
import sys
import time

MUTEX_NAME = "Local\\MyUsageMonitor_SingleInstance"
ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    """`acquire()` 回傳 False 表示已經有另一份在執行。物件存活期間持有 mutex。"""

    def __init__(self, name: str = MUTEX_NAME) -> None:
        self.name = name
        self._handle: int | None = None

    def acquire(self, wait: float = 0.0) -> bool:
        """`wait` 秒內一直重試（「立即更新」啟動的新版要等舊版結束、放掉 mutex）。"""
        deadline = time.monotonic() + wait
        while not self._try_acquire():
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.25)
        return True

    def _try_acquire(self) -> bool:
        if sys.platform != "win32":
            return True
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, self.name)
        already = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
        if not handle:
            return True  # 建不出 mutex 時不要擋住使用者
        if already:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is not None and sys.platform == "win32":
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self._handle))
            self._handle = None
