"""睡眠喚醒通知（WM_POWERBROADCAST）。

Windows 會把這個訊息送給所有最上層視窗；UI 端用 Qt 的 native event filter 接收。
Modern Standby 的電腦不一定會送，所以排程本身另有每分鐘比對時間的保險
（scheduler.MAX_WAIT_SECONDS）。
"""

from __future__ import annotations

import sys

WM_POWERBROADCAST = 0x0218
PBT_APMRESUMEAUTOMATIC = 0x0012
"""每次喚醒都會送（有沒有使用者操作都一樣），只認這個就不會重複觸發。"""


def is_resume_message(msg_address: int) -> bool:
    """Qt native event filter 收到的 MSG 指標是不是「剛從睡眠喚醒」。"""
    if sys.platform != "win32" or not msg_address:
        return False
    from ctypes import wintypes

    msg = wintypes.MSG.from_address(msg_address)
    return msg.message == WM_POWERBROADCAST and msg.wParam == PBT_APMRESUMEAUTOMATIC
