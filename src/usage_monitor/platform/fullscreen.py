"""前景視窗是否為全螢幕（無邊框全螢幕的遊戲、影片）。

有標題列的視窗不算全螢幕，即使它最大化、矩形蓋滿螢幕（例如工作列自動隱藏時）；
沒有標題列、蓋滿整個螢幕的才算，不管是不是最大化。瀏覽器從最大化狀態讓影片進入
全螢幕時仍然保留最大化狀態，所以不能用 IsZoomed 判斷（2026-11-04 bug）。
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

MONITOR_DEFAULTTONEAREST = 2
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
"""WS_BORDER | WS_DLGFRAME；兩個位元都有才是標題列。"""
WS_MAXIMIZE = 0x01000000
_IGNORED_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"})
"""桌面與工作列本身的矩形也會蓋滿螢幕，要排除。"""

Rect = tuple[int, int, int, int]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def covers(window: Rect, monitor: Rect) -> bool:
    """(left, top, right, bottom)：視窗矩形是否蓋滿整個螢幕（含工作列區域）。"""
    return (
        window[0] <= monitor[0]
        and window[1] <= monitor[1]
        and window[2] >= monitor[2]
        and window[3] >= monitor[3]
    )


def is_fullscreen_window(rect: Rect, monitor: Rect, style: int, class_name: str) -> bool:
    """判斷規則本身（純函式，不碰 Win32）：沒有標題列、蓋滿螢幕，且不是桌面或工作列。"""
    if class_name in _IGNORED_CLASSES:
        return False
    if style & WS_CAPTION == WS_CAPTION:
        return False
    return covers(rect, monitor)


def is_foreground_fullscreen() -> bool:
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        return False

    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    user32.GetWindowLongW.restype = ctypes.c_long
    style = user32.GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF

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
    return is_fullscreen_window(
        (rect.left, rect.top, rect.right, rect.bottom),
        (m.left, m.top, m.right, m.bottom),
        style,
        cls.value,
    )
