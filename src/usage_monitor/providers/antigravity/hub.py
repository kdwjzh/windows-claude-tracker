"""找到執行中的 Antigravity language server：`~/.gemini/antigravity/daemon/hub_*.json`。

Antigravity 啟動時寫這個檔（`pid`、`httpPort`、`csrfToken`）。只讀不寫；
當掉時會留下舊檔，所以 pid 已結束的檔案跳過。csrf token 只送到 127.0.0.1，也不進 log。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from usage_monitor.core.json_access import as_dict, as_float, as_str
from usage_monitor.platform import paths, process

log = logging.getLogger(__name__)

SOURCE_NAME = "antigravity"


@dataclass(frozen=True)
class Hub:
    pid: int
    port: int
    csrf_token: str = field(repr=False)


def daemon_dir() -> Path:
    return paths.home() / ".gemini" / "antigravity" / "daemon"


def _parse(path: Path) -> Hub | None:
    try:
        data = as_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:
        log.debug("Antigravity hub 檔讀取失敗：%s", type(e).__name__)
        return None
    if data is None:
        return None
    pid = as_float(data.get("pid"))
    port = as_float(data.get("httpPort"))
    token = (as_str(data.get("csrfToken")) or "").strip()
    if pid is None or port is None or not token or not 0 < port <= 65535:
        return None
    return Hub(int(pid), int(port), token)


class HubSource:
    name = SOURCE_NAME

    def __init__(
        self,
        directory: Path | None = None,
        is_running: Callable[[int], bool] = process.is_running,
    ) -> None:
        self._dir = directory
        self._is_running = is_running

    @property
    def directory(self) -> Path:
        return self._dir or daemon_dir()

    def _files(self) -> list[Path]:
        try:
            return sorted(self.directory.glob("hub_*.json"))
        except OSError:
            return []

    def read(self) -> Hub | None:
        """執行中的 hub；有好幾個時取最新寫入的。沒有時 None。"""
        candidates: list[tuple[int, Hub]] = []
        for path in self._files():
            hub = _parse(path)
            if hub is None or not self._is_running(hub.pid):
                continue
            try:
                mtime = path.stat().st_mtime_ns
            except OSError:
                continue
            candidates.append((mtime, hub))
        return max(candidates, key=lambda c: c[0])[1] if candidates else None

    def signature(self) -> str:
        parts: list[str] = []
        for path in self._files():
            try:
                st = path.stat()
            except OSError:
                continue
            parts.append(f"{path.name}|{st.st_size}|{st.st_mtime_ns}")
        return ";".join(parts) or f"{self.directory}|missing"
