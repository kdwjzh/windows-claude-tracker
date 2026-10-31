"""settings.json 的讀寫。

- 檔案不存在：寫出預設值
- 格式錯誤：用預設值啟動並記 log；壞掉的檔案另存成 `settings.json.broken`，不直接覆蓋
- 舊版本：自動遷移並寫回
- 寫入是原子的：先寫暫存檔再取代，不會因為當機留下寫一半的檔案
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from collections.abc import Callable, Mapping
from pathlib import Path

from usage_monitor.core.json_access import as_dict
from usage_monitor.services.settings.migrations import (
    MIGRATIONS,
    FutureVersionError,
    Migration,
    migrate,
    version_of,
)
from usage_monitor.services.settings.schema import CURRENT_VERSION, Settings, settings_from_dict
from usage_monitor.services.subscribers import Subscribers

log = logging.getLogger(__name__)


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class SettingsStore:
    def __init__(
        self,
        path: Path,
        *,
        target_version: int = CURRENT_VERSION,
        migrations: Mapping[int, Migration] = MIGRATIONS,
    ) -> None:
        self.path = path
        self._target = target_version
        self._migrations = migrations
        self._lock = threading.Lock()
        self._current = Settings()
        self._subscribers: Subscribers[Settings] = Subscribers()

    @property
    def current(self) -> Settings:
        return self._current

    def load(self) -> Settings:
        """讀檔並回傳設定；任何問題都不丟例外。"""
        with self._lock:
            self._current = self._load()
            return self._current

    def _load(self) -> Settings:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            log.info("設定檔不存在，寫出預設值：%s", self.path)
            return self._try_write(Settings())
        except OSError as e:
            log.warning("設定檔讀不到（%s），使用預設值", type(e).__name__)
            return Settings()

        try:
            raw = as_dict(json.loads(text))
        except ValueError:
            raw = None
        if raw is None:
            self._backup_broken()
            log.warning("設定檔格式錯誤，使用預設值；原檔另存為 %s", self._broken_path().name)
            return Settings()

        original_version = version_of(raw)
        try:
            data = migrate(raw, target=self._target, migrations=self._migrations)
        except FutureVersionError as e:
            # 新版程式寫的設定：讀得懂的欄位照用，但不寫回，避免把新欄位弄丟
            log.warning("%s；只讀取認得的欄位，不寫回", e)
            settings, warnings = settings_from_dict(raw)
            self._log_warnings(warnings)
            return settings

        settings, warnings = settings_from_dict(data)
        self._log_warnings(warnings)
        if original_version != self._target:
            log.info("設定檔從 v%d 遷移到 v%d", original_version, self._target)
            self._try_write(settings)
        return settings

    @staticmethod
    def _log_warnings(warnings: list[str]) -> None:
        for w in warnings:
            log.warning(w)

    def _broken_path(self) -> Path:
        return self.path.with_name(self.path.name + ".broken")

    def _backup_broken(self) -> None:
        try:
            self._broken_path().write_bytes(self.path.read_bytes())
        except OSError as e:
            log.warning("無法備份壞掉的設定檔：%s", type(e).__name__)

    def _try_write(self, settings: Settings) -> Settings:
        try:
            self._write(settings)
        except OSError as e:
            log.warning("設定檔寫不進去（%s）", type(e).__name__)
        return settings

    def _write(self, settings: Settings) -> None:
        data = {**settings.to_dict(), "schema_version": self._target}
        write_atomic(self.path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    def save(self, settings: Settings) -> None:
        """寫入並通知訂閱者；寫入失敗時丟 OSError，記憶體中的設定不變。"""
        with self._lock:
            self._write(settings)
            self._current = settings
        self._subscribers.notify(settings)

    def update(self, change: Callable[[Settings], Settings]) -> Settings:
        """以目前設定為基礎修改並儲存，例如 `store.update(lambda s: replace(s, ...))`。"""
        with self._lock:
            new = change(self._current)
            self._write(new)
            self._current = new
        self._subscribers.notify(new)
        return new

    def subscribe(self, callback: Callable[[Settings], None]) -> Callable[[], None]:
        return self._subscribers.add(callback)
