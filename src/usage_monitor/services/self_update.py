"""「立即更新」的下載與核對（ADR 0007）：下載新版 exe 到舊 exe 的資料夾，核對 SHA-256 後才留下。

- 只下載 UpdateChecker 已驗證過的本 repo Release 附件網址，不帶任何 token
- GitHub 的下載連結會轉址到 *.githubusercontent.com；共用的 Transport 不跟隨轉址（保護 token），
  所以這裡自己一步步跟，每一步都檢查主機只能是 github.com 或 *.githubusercontent.com
- 先寫成暫存檔，核對通過才改成正式檔名；失敗時刪掉暫存檔
- 啟動新版、結束舊版、刪舊檔是 platform/relaunch.py 的事；這裡不碰程序，可以在 Linux 測
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
from enum import Enum
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from usage_monitor.core import app_info
from usage_monitor.core.errors import PollError
from usage_monitor.core.interfaces import Transport
from usage_monitor.services.update_check import UpdateState

log = logging.getLogger(__name__)

TIMEOUT = 30.0
MAX_REDIRECTS = 5
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class InstallStatus(Enum):
    IDLE = "idle"
    DOWNLOADING = "downloading"
    FAILED = "failed"


class InstallError(Exception):
    """下載或核對失敗；訊息只給 log 用（不含網址以外的資料）。"""


def _allowed(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (
        host == "github.com" or host.endswith(".githubusercontent.com")
    )


def fetch(transport: Transport, url: str, user_agent: str) -> bytes:
    """GET 一個 Release 附件，自己跟隨轉址（只到允許的主機）。"""
    for _ in range(MAX_REDIRECTS + 1):
        if not _allowed(url):
            raise InstallError(f"不允許從 {urlsplit(url).hostname} 下載")
        try:
            resp = transport.get(
                url,
                {"User-Agent": user_agent, "Accept": "application/octet-stream"},
                timeout=TIMEOUT,
            )
        except PollError as e:
            raise InstallError(f"下載連線失敗：{e}") from e
        if resp.status in REDIRECT_STATUSES:
            location = resp.header("Location")
            if not location:
                raise InstallError(f"轉址沒有 Location（HTTP {resp.status}）")
            url = urljoin(url, location)
            continue
        if resp.status != 200:
            raise InstallError(f"下載失敗（HTTP {resp.status}）")
        return resp.body
    raise InstallError("轉址次數太多")


def expected_hash(sums: bytes, name: str) -> str | None:
    """從 SHA256SUMS.txt（`<hex>  <檔名>` 一行一個）找出檔案的雜湊。"""
    for line in sums.decode("utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    return None


def download_update(transport: Transport, state: UpdateState, target_dir: Path) -> Path:
    """下載並核對新版 exe，放到 target_dir；回傳新檔案路徑。失敗丟 InstallError。"""
    version = state.latest_version
    if version is None or state.exe_url is None or state.sums_url is None:
        raise InstallError("Release 沒有可下載的 exe 或 SHA256SUMS.txt")
    name = app_info.exe_name(version)
    user_agent = f"{app_info.REPO_NAME}/{state.current_version}"
    log.info("下載新版 %s", name)
    sums = fetch(transport, state.sums_url, user_agent)
    expected = expected_hash(sums, name)
    if expected is None:
        raise InstallError(f"SHA256SUMS.txt 裡沒有 {name}")
    body = fetch(transport, state.exe_url, user_agent)
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected:
        raise InstallError(f"{name} 的 SHA-256 不符")

    final = target_dir / name
    temp = target_dir / f"{name}.download"
    try:
        temp.write_bytes(body)
        temp.replace(final)
    except OSError as e:
        with contextlib.suppress(OSError):
            temp.unlink()
        raise InstallError(f"寫不進 {target_dir}：{type(e).__name__}") from e
    log.info("新版已下載並核對：%s", final)
    return final
