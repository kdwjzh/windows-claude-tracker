"""前景視窗是否為全螢幕（無邊框全螢幕的遊戲、影片）。視窗最大化不算全螢幕。"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

MONITOR_DEFAULTTONEAREST = 2
_IGNORED_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"})
"""桌面與工作列本身的矩形也會蓋滿螢幕，要排除。"""


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def covers(window: tuple[int, int, int, int], monitor: tuple[int, int, int, int]) -> bool:
    """(left, top, right, bottom)：視窗矩形是否蓋滿整個螢幕（含工作列區域）。"""
    return (
        window[0] <= monitor[0]
        and window[1] <= monitor[1]
        and window[2] >= monitor[2]
        and window[3] >= monitor[3]
    )


def is_foreground_fullscreen() -> bool:
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    hwnd = user32.GetForegroundWindow()
    if not hwnd or user32.IsZoomed(hwnd):
        return False

    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    if cls.value in _IGNORED_CLASSES:
        return False

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        return False

    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(_MonitorInfo)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return False
    m = info.rcMonitor
    return covers(
        (rect.left, rect.top, rect.right, rect.bottom), (m.left, m.top, m.right, m.bottom)
    )
