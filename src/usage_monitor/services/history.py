"""用量歷史紀錄：每次成功輪詢記一筆到 sqlite3（%APPDATA%\\MyUsageMonitor\\history.db）。

- 只存服務、週期、百分比、時間與重置時間；不存 token、帳號或任何對話內容
- 訂閱 StateStore（在輪詢執行緒上呼叫）；失敗或資料過期（stale）時不記，避免重複
- 保留 RETENTION_DAYS 天，每次寫入時順便刪掉更舊的
- 任何資料庫錯誤只記 log，不影響輪詢；「清除歷史紀錄」直接刪檔，檔案壞掉也能藉此恢復
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from usage_monitor.core.interfaces import Clock
from usage_monitor.core.models import ProviderState

log = logging.getLogger(__name__)

RETENTION_DAYS = 90

_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    provider TEXT NOT NULL,
    window TEXT NOT NULL,
    label TEXT,
    fetched_at REAL NOT NULL,
    percent REAL NOT NULL,
    resets_at REAL
);
CREATE INDEX IF NOT EXISTS samples_by_time ON samples (provider, fetched_at);
"""


@dataclass(frozen=True)
class Sample:
    provider_id: str
    window: str
    """"session"（短週期）或 "long"（7d／30d）。"""
    label: str | None
    fetched_at: datetime
    percent: float
    resets_at: datetime | None


def _ts(moment: datetime) -> float:
    return moment.timestamp()


def _dt(value: float | None) -> datetime | None:
    return None if value is None else datetime.fromtimestamp(value, UTC)


class History:
    def __init__(self, path: Path, clock: Clock) -> None:
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()
        self._last: dict[str, datetime] = {}
        """每個服務最後記錄的 fetched_at：同一筆資料再通知一次時不重複記。"""

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self._path, timeout=5)
        try:
            db.executescript(_SCHEMA)
        except sqlite3.Error:
            db.close()  # 不關的話 Windows 上檔案一直被占用，「清除」就刪不掉
            raise
        return db

    def record(self, state: ProviderState) -> None:
        usage = state.usage
        if usage is None or state.error is not None or state.stale:
            return
        if self._last.get(state.provider_id) == usage.fetched_at:
            return
        rows = [
            (state.provider_id, name, w.label, _ts(usage.fetched_at), w.percent,
             _ts(w.resets_at) if w.resets_at else None)
            for name, w in (("session", usage.session), ("long", usage.long))
            if w.available
        ]  # fmt: skip
        cutoff = _ts(self._clock.now() - timedelta(days=RETENTION_DAYS))
        with self._lock:
            try:
                with closing(self._connect()) as db, db:
                    db.executemany("INSERT INTO samples VALUES (?, ?, ?, ?, ?, ?)", rows)
                    db.execute("DELETE FROM samples WHERE fetched_at < ?", (cutoff,))
            except (sqlite3.Error, OSError):
                log.warning("用量歷史寫不進去", exc_info=True)
                return
            self._last[state.provider_id] = usage.fetched_at

    def samples(self, provider_id: str, since: datetime) -> list[Sample]:
        """某個服務 `since` 之後的紀錄，依時間排序；讀不到時回傳空清單。"""
        with self._lock:
            try:
                with closing(self._connect()) as db:
                    rows = db.execute(
                        "SELECT * FROM samples WHERE provider = ? AND fetched_at >= ?"
                        " ORDER BY fetched_at, rowid",
                        (provider_id, _ts(since)),
                    ).fetchall()
            except (sqlite3.Error, OSError):
                log.warning("用量歷史讀不到", exc_info=True)
                return []
        return [
            Sample(pid, window, label, datetime.fromtimestamp(at, UTC), percent, _dt(resets))
            for pid, window, label, at, percent, resets in rows
        ]

    def clear(self) -> None:
        """刪掉整個資料庫檔案（設定視窗「清除歷史紀錄」）。"""
        with self._lock:
            try:
                self._path.unlink(missing_ok=True)
            except OSError:
                log.warning("用量歷史刪不掉", exc_info=True)
                return
        log.info("已清除用量歷史")
