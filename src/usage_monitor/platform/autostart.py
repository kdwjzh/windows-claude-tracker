"""開機啟動：HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run（不需系統管理員權限）。"""

from __future__ import annotations

import contextlib
import logging
import sys
from collections.abc import Callable
from pathlib import PureWindowsPath

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "MyUsageMonitor"


def command(executable: str | None = None, frozen: bool | None = None) -> str:
    """登錄檔要寫的指令。

    - PyInstaller 打包：直接執行 exe
    - 原始碼執行：用同一個環境的 pythonw.exe（不跳主控台）跑 `-m usage_monitor`
    """
    exe = PureWindowsPath(executable or sys.executable)
    is_frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if is_frozen:
        return f'"{exe}"'
    pythonw = exe.with_name("pythonw.exe") if exe.name.lower() == "python.exe" else exe
    return f'"{pythonw}" -m usage_monitor'


def registered_command() -> str | None:
    """登錄檔目前寫的指令；沒啟用（或讀不到）回傳 None。"""
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
    except OSError:
        return None
    return str(value)


def is_enabled() -> bool:
    return registered_command() is not None


def sync_command(
    read: Callable[[], str | None] = registered_command,
    write: Callable[[], None] = lambda: set_enabled(True),
) -> bool:
    """已啟用但指向別的 exe（例如換了新版，檔名帶版本號）時改寫成目前的指令。

    有改寫回傳 True；失敗只記 log，不丟例外。
    """
    registered = read()
    if registered is None or registered.casefold() == command().casefold():
        return False
    try:
        write()
    except OSError:
        log.warning("開機啟動指向舊的執行檔，改寫失敗", exc_info=True)
        return False
    log.info("開機啟動指向舊的執行檔，已改成目前的版本")
    return True


def set_enabled(enabled: bool) -> None:
    """失敗時丟 OSError。"""
    if sys.platform != "win32":
        raise OSError("開機啟動只支援 Windows")
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
            log.info("已啟用開機啟動")
        else:
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteValue(key, VALUE_NAME)
            log.info("已停用開機啟動")
