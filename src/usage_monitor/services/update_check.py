"""更新檢查（CLAUDE.md §3.9）：查 GitHub 最新 Release，有比目前新的正式版就提醒。

- 只連 api.github.com，不帶任何 token、帳號或用量資料
- 啟動 30 秒後一次、之後每 24 小時一次；`enabled=False` 時只有手動按才查
- 404（尚無 Release 或 API 暫時無法使用）、403／429（次數限制）、網路錯誤 → 「目前無法檢查」，
  不通知、不顯示錯誤，只記 debug log
- 不下載任何東西：只回報 Release 頁面網址，由使用者自己開
- 邏輯集中在 `tick()`，用 FakeClock＋FakeTransport 就能測
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum

from usage_monitor.core import app_info, semver
from usage_monitor.core.errors import PollError
from usage_monitor.core.interfaces import Clock, Transport
from usage_monitor.core.json_access import as_dict, as_str
from usage_monitor.services.settings.schema import Settings, UpdateCheckSettings
from usage_monitor.services.settings.store import SettingsStore
from usage_monitor.services.subscribers import Subscribers

log = logging.getLogger(__name__)

STARTUP_DELAY = timedelta(seconds=30)
CHECK_INTERVAL = timedelta(hours=24)
IDLE_WAKE = timedelta(hours=1)
"""自動檢查關閉時，多久醒來一次看看設定有沒有被打開。"""
TIMEOUT = 30.0


class UpdateStatus(Enum):
    UNKNOWN = "unknown"
    """還沒檢查過。"""
    CHECKING = "checking"
    UP_TO_DATE = "up_to_date"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    """目前無法檢查（尚無 Release、次數限制、網路錯誤）。"""


@dataclass(frozen=True)
class UpdateState:
    current_version: str
    status: UpdateStatus = UpdateStatus.UNKNOWN
    latest_version: str | None = None
    url: str = app_info.RELEASES_URL
    """Release 頁面；一定是本 repo 底下的網址。"""
    skipped: bool = False
    """latest_version 是使用者略過的版本。"""

    @property
    def should_alert(self) -> bool:
        """系統匣選單項目、藍點：有新版且沒有被略過。"""
        return self.status is UpdateStatus.AVAILABLE and not self.skipped


def _safe_url(value: object) -> str:
    """只接受本 repo 的 Release 頁面，避免回應被竄改時開到別的網站。"""
    url = as_str(value) or ""
    return url if url.startswith(app_info.RELEASES_URL + "/") else app_info.RELEASES_URL


class UpdateChecker:
    def __init__(
        self,
        transport: Transport,
        clock: Clock,
        settings: SettingsStore,
        current_version: str,
    ) -> None:
        self._transport = transport
        self._clock = clock
        self._settings = settings
        self._state = UpdateState(current_version=current_version)
        self._subscribers: Subscribers[UpdateState] = Subscribers()
        self._lock = threading.Lock()
        self._force = False
        self._next_due = clock.now() + STARTUP_DELAY
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------------------------------------------------------------- 對外

    @property
    def state(self) -> UpdateState:
        return self._state

    def subscribe(self, callback: Callable[[UpdateState], None]) -> Callable[[], None]:
        return self._subscribers.add(callback)

    def check_now(self) -> None:
        """「關於」頁的「檢查更新」：不管設定與排程，立即在背景檢查一次。"""
        self._force = True
        self._wake.set()

    def settings_changed(self) -> None:
        """設定改了（例如重新打開自動檢查、略過版本）：重新評估狀態並喚醒排程。"""
        self._set_state(self._with_skip(self._state, self._settings.current))
        self._wake.set()

    def skip_latest(self) -> None:
        """「略過這個版本」：記下目前的最新版，之後不再提醒；更新的版本照常提醒。"""
        version = self._state.latest_version
        if version is None:
            return
        self._update_settings(lambda u: replace(u, skipped_version=version))
        self._set_state(replace(self._state, skipped=True))

    def claim_notification(self) -> str | None:
        """該不該發 Windows 通知：每個新版本只回傳一次版本號，並記在設定裡。"""
        state = self._state
        version = state.latest_version
        if not state.should_alert or version is None:
            return None
        if self._settings.current.update_check.notified_version == version:
            return None
        self._update_settings(lambda u: replace(u, notified_version=version))
        return version

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="update-check", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)

    # ---------------------------------------------------------------- 排程

    def tick(self) -> datetime:
        """到期（或手動要求）就檢查；回傳下次要醒來的時間。"""
        with self._lock:
            force, self._force = self._force, False
            now = self._clock.now()
            enabled = self._settings.current.update_check.enabled
            if force or (enabled and now >= self._next_due):
                self.check()
                self._next_due = self._clock.now() + CHECK_INTERVAL
            if not enabled:
                return self._clock.now() + IDLE_WAKE
            return self._next_due

    def check(self) -> UpdateState:
        """查一次 GitHub（在呼叫端的執行緒上；背景執行緒呼叫）。"""
        previous = self._state
        self._set_state(replace(previous, status=UpdateStatus.CHECKING))
        try:
            resp = self._transport.get(
                app_info.LATEST_RELEASE_API,
                {
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"{app_info.REPO_NAME}/{previous.current_version}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=TIMEOUT,
            )
            data = as_dict(resp.json()) if resp.status == 200 else None
        except (PollError, ValueError) as e:
            log.debug("更新檢查連線失敗：%s", e)
            data = None
            resp = None
        if data is None:
            if resp is not None:
                log.debug("更新檢查無法取得 Release（HTTP %s）", resp.status)
            # 這次查不到，但先前已經知道有新版：保留提醒
            status = (
                UpdateStatus.AVAILABLE
                if previous.status is UpdateStatus.AVAILABLE
                else UpdateStatus.UNAVAILABLE
            )
            return self._set_state(replace(previous, status=status))

        self._update_settings(lambda u: replace(u, last_checked_at=self._clock.now().isoformat()))
        tag = as_str(data.get("tag_name"))
        unofficial = data.get("prerelease") is True or data.get("draft") is True
        if not unofficial and semver.is_newer_release(tag, previous.current_version):
            latest = str(semver.parse(tag))
            log.info("有新版本 %s（目前 %s）", latest, previous.current_version)
            state = UpdateState(
                current_version=previous.current_version,
                status=UpdateStatus.AVAILABLE,
                latest_version=latest,
                url=_safe_url(data.get("html_url")),
            )
            return self._set_state(self._with_skip(state, self._settings.current))
        return self._set_state(
            UpdateState(current_version=previous.current_version, status=UpdateStatus.UP_TO_DATE)
        )

    # ---------------------------------------------------------------- 內部

    @staticmethod
    def _with_skip(state: UpdateState, settings: Settings) -> UpdateState:
        skipped = (
            state.latest_version is not None
            and state.latest_version == settings.update_check.skipped_version
        )
        return replace(state, skipped=skipped)

    def _set_state(self, state: UpdateState) -> UpdateState:
        if state != self._state:
            self._state = state
            self._subscribers.notify(state)
        return state

    def _update_settings(
        self, change: Callable[[UpdateCheckSettings], UpdateCheckSettings]
    ) -> None:
        def apply(s: Settings) -> Settings:
            return replace(s, update_check=change(s.update_check))

        try:
            self._settings.update(apply)
        except OSError as e:
            log.warning("更新檢查的設定寫不進去：%s", type(e).__name__)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                wake_at = self.tick()
            except Exception:
                log.exception("更新檢查發生未預期錯誤")
                wake_at = self._clock.now() + IDLE_WAKE
            timeout = max(0.0, (wake_at - self._clock.now()).total_seconds())
            self._wake.wait(timeout)
            self._wake.clear()
