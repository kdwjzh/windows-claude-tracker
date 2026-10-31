"""開啟檔案、啟動診斷工具。"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path, PureWindowsPath

log = logging.getLogger(__name__)

CREATE_NEW_CONSOLE = 0x00000010


def open_path(path: Path) -> None:
    """用預設程式開啟檔案或資料夾（例如 log）。"""
    if sys.platform != "win32":
        return
    try:
        os.startfile(path)
    except OSError as e:
        log.warning("無法開啟 %s：%s", path, type(e).__name__)


def open_url(url: str) -> None:
    """用預設瀏覽器開啟網址；只接受 https。"""
    if not url.startswith("https://"):
        log.warning("拒絕開啟非 https 網址")
        return
    if sys.platform != "win32":
        return
    try:
        os.startfile(url)
    except OSError as e:
        log.warning("無法開啟網址：%s", type(e).__name__)


def find_diagnose_exe(folder: Path) -> Path | None:
    """同資料夾的 diagnose.exe；沒有的話找 Release 下載的 diagnose-vX.Y.Z.exe（取最新修改的）。"""
    plain = folder / "diagnose.exe"
    if plain.is_file():
        return plain
    try:
        versioned = [p for p in folder.glob("diagnose-v*.exe") if p.is_file()]
    except OSError:
        return None
    return max(versioned, key=lambda p: p.stat().st_mtime, default=None)


def diagnose_command(
    executable: str | None = None,
    frozen: bool | None = None,
    find: Callable[[Path], Path | None] = find_diagnose_exe,
) -> list[str]:
    """打包版執行同資料夾的診斷 exe；原始碼版用 python.exe（不是 pythonw）跑模組。"""
    exe = PureWindowsPath(executable or sys.executable)
    is_frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if is_frozen:
        found = find(Path(str(exe.parent)))
        return [str(found) if found else str(exe.with_name("diagnose.exe"))]
    python = exe.with_name("python.exe") if exe.name.lower() == "pythonw.exe" else exe
    return [str(python), "-m", "usage_monitor.diagnose"]


def run_diagnose() -> None:
    """在新的主控台視窗跑診斷，跑完停住讓使用者看結果。

    這是唯一刻意顯示視窗的外部程式，所以不用 CREATE_NO_WINDOW；由使用者自行關閉，不設 timeout。
    """
    if sys.platform != "win32":
        return
    cmd = subprocess.list2cmdline(diagnose_command())
    try:
        subprocess.Popen(
            ["cmd.exe", "/d", "/k", cmd],
            creationflags=CREATE_NEW_CONSOLE,
            close_fds=True,
        )
    except OSError as e:
        log.warning("無法啟動診斷：%s", type(e).__name__)
