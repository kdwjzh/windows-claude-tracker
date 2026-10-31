"""讓 Claude Code CLI 自己更新過期的 token（CLAUDE.md 階段 7；設定 allow_cli_refresh，預設關閉）。

做法：執行 `claude -p . --no-session-persistence`，CLI 啟動時會用它自己的 refresh token
更新並寫回 .credentials.json，之後重新讀檔即可。**本程式從不碰 refresh token。**

- 會用掉一點額度，所以：只在沒有其他可用 token 時才執行、兩次之間至少隔 30 分鐘
- 外部程式一律 CREATE_NO_WINDOW＋timeout（CLAUDE.md §5.2 第 10 條）
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from datetime import datetime, timedelta

from usage_monitor.core.interfaces import Clock

log = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000
MIN_VERSION = (2, 0, 63)
"""比這版舊的 CLI 不支援 --no-session-persistence。"""
VERSION_TIMEOUT = 15.0
REFRESH_TIMEOUT = 90.0
MIN_INTERVAL = timedelta(minutes=30)
REFRESH_ARGS = ("-p", ".", "--no-session-persistence")

Runner = Callable[[list[str], float], "tuple[int, str]"]
"""(指令, timeout) → (exit code, stdout)；逾時或無法執行時丟 OSError／subprocess.TimeoutExpired。"""


def parse_version(text: str) -> tuple[int, int, int] | None:
    """ "2.0.63 (Claude Code)" → (2, 0, 63)。"""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def find_claude(which: Callable[[str], str | None] = shutil.which) -> list[str] | None:
    """找 claude 執行檔；npm 安裝的 .cmd 要透過 cmd.exe 執行。"""
    exe = which("claude.cmd") or which("claude")
    if exe is None:
        return None
    if exe.lower().endswith((".cmd", ".bat")):
        return ["cmd.exe", "/d", "/c", exe]
    return [exe]


def run_hidden(cmd: list[str], timeout: float) -> tuple[int, str]:
    """不跳視窗地執行；工作目錄用暫存資料夾，避免 CLI 讀到某個專案的設定。"""
    proc = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=tempfile.gettempdir(),
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    return proc.returncode, proc.stdout or ""


class ClaudeCliRefresher:
    """呼叫一次就嘗試更新一次（受 30 分鐘間隔限制）；成功回傳 True。不丟例外。"""

    def __init__(
        self,
        clock: Clock,
        *,
        which: Callable[[str], str | None] = shutil.which,
        run: Runner = run_hidden,
    ) -> None:
        self._clock = clock
        self._which = which
        self._run = run
        self._last_attempt: datetime | None = None
        self._version_ok: bool | None = None

    def __call__(self) -> bool:
        now = self._clock.now()
        if self._last_attempt is not None and now - self._last_attempt < MIN_INTERVAL:
            log.debug("距離上次 CLI 更新不到 %s，略過", MIN_INTERVAL)
            return False
        self._last_attempt = now

        cmd = find_claude(self._which)
        if cmd is None:
            log.info("找不到 claude 指令，無法更新 CLI token")
            return False
        if not self._check_version(cmd):
            return False

        log.info("CLI token 已過期，執行 claude 讓它更新（會用掉少量額度）")
        try:
            code, _ = self._run([*cmd, *REFRESH_ARGS], REFRESH_TIMEOUT)
        except subprocess.TimeoutExpired:
            log.warning("claude 更新逾時（%.0f 秒）", REFRESH_TIMEOUT)
            return False
        except OSError as e:
            log.warning("無法執行 claude：%s", type(e).__name__)
            return False
        if code != 0:
            log.warning("claude 更新失敗，結束代碼 %d", code)
            return False
        log.info("claude 執行完成，重新讀取 CLI 憑證")
        return True

    def _check_version(self, cmd: list[str]) -> bool:
        if self._version_ok is not None:
            return self._version_ok
        try:
            code, out = self._run([*cmd, "--version"], VERSION_TIMEOUT)
        except (subprocess.TimeoutExpired, OSError) as e:
            log.warning("無法取得 claude 版本：%s", type(e).__name__)
            return False  # 暫時性問題，下次再檢查
        version = parse_version(out) if code == 0 else None
        if version is None:
            log.warning("看不懂 claude 版本輸出")
            return False
        self._version_ok = version >= MIN_VERSION
        if not self._version_ok:
            log.warning(
                "claude 版本 %s 太舊（需要 %s 以上），無法自動更新 token",
                ".".join(map(str, version)),
                ".".join(map(str, MIN_VERSION)),
            )
        return self._version_ok
