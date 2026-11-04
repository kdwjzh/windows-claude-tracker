"""「立即更新」的交接（ADR 0007）：舊版啟動新版 exe 後結束，新版等舊版結束再刪掉舊檔。

新舊檔名不同（檔名帶版本號），所以不會覆寫正在執行的檔案，也不需要批次檔。
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from usage_monitor.core import app_info

log = logging.getLogger(__name__)

REPLACED_FLAG = "--replaced"
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
_OWN_EXE = re.compile(rf"^{app_info.EXE_PREFIX}[\w.\-() ]*\.exe$", re.IGNORECASE)


def frozen_exe() -> Path | None:
    """打包版正在執行的 exe；用原始碼執行（python -m）時是 None，只能改開 Release 頁。"""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable)


def start_replacement(new_exe: Path, old_exe: Path) -> None:
    """啟動新版並告訴它舊檔在哪；失敗丟 OSError。

    新版是長駐程式，所以這裡不等它結束（CLAUDE.md §5.2 第 10 條的逾時不適用）。
    PYINSTALLER_RESET_ENVIRONMENT：讓新的 onefile exe 自己解壓，不沿用舊版的暫存資料夾。
    """
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    subprocess.Popen(
        [str(new_exe), REPLACED_FLAG, str(old_exe)],
        cwd=str(new_exe.parent),
        env=env,
        creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    log.info("已啟動新版 %s", new_exe.name)


def replaced_path(argv: Sequence[str]) -> Path | None:
    """新版啟動時帶的 `--replaced <舊 exe>`；沒有就是 None。"""
    try:
        i = list(argv).index(REPLACED_FLAG)
    except ValueError:
        return None
    return Path(argv[i + 1]) if i + 1 < len(argv) else None


def remove_replaced(
    old: Path,
    current: Path,
    *,
    attempts: int = 20,
    delay: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """刪掉被取代的舊 exe：只刪同一個資料夾裡、檔名像本程式、而且不是自己的那個檔案。

    舊版剛結束時檔案可能還被鎖住（防毒掃描、程序收尾），所以重試幾次；刪不掉只記 log。
    """
    try:
        same_dir = old.resolve().parent == current.resolve().parent
        is_self = old.resolve() == current.resolve()
    except OSError:
        return False
    if not same_dir or is_self or not _OWN_EXE.match(old.name):
        log.warning("不刪除舊版：%s 不在同一個資料夾或不是本程式的檔名", old.name)
        return False
    for i in range(attempts):
        try:
            old.unlink()
        except FileNotFoundError:
            return True
        except OSError:
            if i + 1 < attempts:
                sleep(delay)
            continue
        log.info("已刪除舊版 %s", old.name)
        return True
    log.warning("舊版 %s 刪不掉（可能還在使用中），請手動刪除", old.name)
    return False
