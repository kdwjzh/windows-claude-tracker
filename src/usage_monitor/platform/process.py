"""某個程序是否還在執行（Antigravity 當掉時會留下舊的 hub_*.json，要靠 pid 認出來）。"""

from __future__ import annotations

import ctypes
import os
import sys

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
ERROR_ACCESS_DENIED = 5


def is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        # 權限不足代表程序存在；其他錯誤（找不到）代表已結束
        return kernel32.GetLastError() == ERROR_ACCESS_DENIED
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)
