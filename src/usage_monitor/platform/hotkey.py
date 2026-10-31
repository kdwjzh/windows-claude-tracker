"""全域快捷鍵（RegisterHotKey）。

註冊到某個視窗後，Windows 會送 WM_HOTKEY 給那個視窗；UI 端用 Qt 的 native event filter 接收。
"""

from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
}


def parse(hotkey: str) -> tuple[int, int]:
    """ "Ctrl+Alt+U" → (modifiers, virtual key)。不合法時丟 ValueError。

    支援 A–Z、0–9、F1–F24；至少要有一個修飾鍵，避免攔截一般打字。
    """
    parts = [p.strip().lower() for p in hotkey.split("+") if p.strip()]
    if not parts:
        raise ValueError("快捷鍵是空的")
    *mods, key = parts
    modifiers = MOD_NOREPEAT
    for m in mods:
        if m not in _MODIFIERS:
            raise ValueError(f"不認得的修飾鍵：{m}")
        modifiers |= _MODIFIERS[m]
    if modifiers == MOD_NOREPEAT:
        raise ValueError("快捷鍵至少要有一個 Ctrl／Alt／Shift／Win")
    if len(key) == 1 and key.isascii() and key.isalnum():
        return modifiers, ord(key.upper())
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return modifiers, 0x70 + int(key[1:]) - 1
    raise ValueError(f"不支援的按鍵：{key}")


def register(hwnd: int, hotkey_id: int, hotkey: str) -> bool:
    """註冊失敗（格式錯誤或被其他程式占用）時記 log 並回傳 False，不影響其他功能。"""
    if sys.platform != "win32":
        return False
    try:
        modifiers, vk = parse(hotkey)
    except ValueError as e:
        log.warning("快捷鍵 %r 無法使用：%s", hotkey, e)
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    if not user32.RegisterHotKey(ctypes.c_void_p(hwnd), hotkey_id, modifiers, vk):
        log.warning(
            "快捷鍵 %s 註冊失敗（可能被其他程式占用），錯誤碼 %d", hotkey, ctypes.get_last_error()
        )
        return False
    log.info("已註冊快捷鍵 %s", hotkey)
    return True


def is_hotkey_message(msg_address: int, hotkey_id: int) -> bool:
    """Qt native event filter 收到的 MSG 指標是不是這個快捷鍵的 WM_HOTKEY。"""
    if sys.platform != "win32" or not msg_address:
        return False
    from ctypes import wintypes

    msg = wintypes.MSG.from_address(msg_address)
    return msg.message == WM_HOTKEY and msg.wParam == hotkey_id


def unregister(hwnd: int, hotkey_id: int) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.UnregisterHotKey(ctypes.c_void_p(hwnd), hotkey_id)
