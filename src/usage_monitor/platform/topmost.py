"""小工具視窗的 Win32 細節：不搶焦點、維持在最上層。"""

from __future__ import annotations

import ctypes
import sys

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200


def _user32() -> ctypes.WinDLL:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    return user32


def make_noactivate(hwnd: int) -> None:
    """點擊小工具不會讓正在打字的視窗失去焦點，也不出現在 Alt+Tab。"""
    if sys.platform != "win32":
        return
    user32 = _user32()
    style = user32.GetWindowLongPtrW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
    user32.SetWindowLongPtrW(
        ctypes.c_void_p(hwnd), GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
    )


def reassert_topmost(hwnd: int) -> None:
    """點擊工作列會蓋過其他置頂視窗，定期重新設回最上層（不移動、不改大小、不啟用）。"""
    if sys.platform != "win32":
        return
    ctypes.windll.user32.SetWindowPos(
        ctypes.c_void_p(hwnd),
        ctypes.c_void_p(HWND_TOPMOST),
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
    )
