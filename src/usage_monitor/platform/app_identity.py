"""Windows 工作列身分（AppUserModelID）：讓視窗用自己的圖示、不跟其他 Python 程式擠成同一組。

必須在建立任何 Qt 視窗之前呼叫（由 __main__.py 最開頭呼叫）。失敗只記 log，不影響啟動。
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Any

from usage_monitor.core.app_info import APP_USER_MODEL_ID

log = logging.getLogger("usage_monitor.platform.app_identity")

_failure: str | None = None
"""apply() 失敗的原因。apply() 在 log 設定好之前就執行，所以由 report() 事後補記。"""


def apply(app_id: str = APP_USER_MODEL_ID, shell32: Any = None) -> bool:
    """呼叫 SetCurrentProcessExplicitAppUserModelID；非 Windows 直接回傳 False。"""
    global _failure
    if sys.platform != "win32" and shell32 is None:
        return False
    try:
        if shell32 is None:
            shell32 = ctypes.windll.shell32
        hr = shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(app_id))
    except Exception as exc:  # 任何失敗都不可讓程式崩潰
        _failure = f"{type(exc).__name__}: {exc}"
    else:
        if hr == 0:
            _failure = None
            return True
        _failure = f"HRESULT 0x{hr & 0xFFFFFFFF:08X}"
    log.warning("無法設定 AppUserModelID：%s", _failure)
    return False


def report() -> None:
    """log 設定好之後呼叫：把 apply() 的失敗補記到 monitor.log。"""
    if _failure is not None:
        log.warning("無法設定 AppUserModelID（工作列可能顯示 Python 圖示）：%s", _failure)
