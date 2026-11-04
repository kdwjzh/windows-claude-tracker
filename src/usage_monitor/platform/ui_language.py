"""Windows 顯示語言（不用 Qt：診斷工具不含 Qt）。"""

from __future__ import annotations

import ctypes
import locale
import sys


def system_ui_languages() -> list[str]:
    """例如 ["zh-TW"]；非 Windows 或查不到時回傳空清單（resolve_language 會當成英文）。"""
    if sys.platform != "win32":
        return []
    langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    name = locale.windows_locale.get(langid)
    return [name.replace("_", "-")] if name else []
