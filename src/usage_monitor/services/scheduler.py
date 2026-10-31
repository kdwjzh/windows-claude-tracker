"""輪詢排程（CLAUDE.md §3.5）。

- 每個服務獨立排程、獨立記錄錯誤與退避；一個服務出任何錯都不影響其他服務
- 只有一條背景執行緒，同時只會有一個輪詢在跑；手動更新用 Event 喚醒
- 排程邏輯集中在 `tick()`，用 FakeClock 就能測，不必真的等待
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.interfaces import Clock, Provider
from usage_monitor.core.models import ProviderState, Usage
from usage_monitor.services.state_store import StateStore

log = logging.getLogger(__name__)

RETRY_BASE_SECONDS = 30.0
AUTH_RECHECK_SECONDS = 60.0
RESET_GRACE_SECONDS = 10.0
MIN_DELAY_SECONDS = 10.0


@dataclass
class _Slot:
    """單一服務的排程狀態（只在排程執行緒內修改）。"""

    provider: Provider
    next_due: datetime
    retries: int = 0
    paused_signature: str | None = None
    """認證錯誤時記下憑證簽章；簽章改變前不打 API。"""
    last_usage: Usage | None = field(default=None)


def backoff_seconds(retries: int, interval: float, retry_after: float | None) -> float:
    """`30s × 2^(n-1)`，上限為輪詢間隔；有 Retry-After 時取較大值。"""
    delay = min(RETRY_BASE_SECONDS * 2 ** (max(retries, 1) - 1), interval)
    return max(delay, retry_after or 0.0)


def next_after_success(usage: Usage, now: datetime, interval: float) -> datetime:
    """一般是 now + 間隔；若任一視窗會在這之前重置，改排在重置後 10 秒，讓畫面馬上歸零。"""
    due = now + timedelta(seconds=interval)
    for window in (usage.session, usage.long):
        if window.resets_at is not None and window.resets_at > now:
            due = min(due, window.resets_at + timedelta(seconds=RESET_GRACE_SECONDS))
    return max(due, now + timedelta(seconds=MIN_DELAY_SECONDS))


class Scheduler:
    def __init__(
        self,
        providers: Sequence[Provider],
        store: StateStore,
        clock: Clock,
        *,
        interval_minutes: float = 5,
    ) -> None:
        now = clock.now()
        self._slots = [_Slot(p, next_due=now) for p in providers]
        self._store = store
        self._clock = clock
        self._interval = interval_minutes * 60
        self._lock = threading.Lock()
        self._force = False
        self._pending: list[Provider] | None = None
        """set_providers 傳進來、還沒套用的服務清單（下一次 tick 開頭套用）。"""
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------------------------------------------------------------- 對外

    @property
    def interval_seconds(self) -> float:
        return self._interval

    def set_interval(self, minutes: float) -> None:
        """改輪詢間隔；已排好的下一次不變，之後的輪詢套用新值。"""
        self._interval = minutes * 60
        self._wake.set()

    def set_providers(self, providers: Sequence[Provider]) -> None:
        """更換要輪詢的服務（設定視窗開關服務時呼叫）。

        不等待正在進行的輪詢：先記下來、喚醒排程執行緒，在下一次 tick 開頭套用。
        既有服務保留排程狀態；新加入的服務立刻輪詢。
        """
        self._pending = list(providers)
        self._wake.set()

    def _apply_pending(self) -> None:
        pending, self._pending = self._pending, None
        if pending is None:
            return
        existing = {slot.provider.id: slot for slot in self._slots}
        now = self._clock.now()
        self._slots = [existing.get(p.id) or _Slot(p, next_due=now) for p in pending]
        log.info("輪詢的服務：%s", [p.id for p in pending] or "（無）")

    def refresh_now(self) -> None:
        """立即更新所有服務（包括因認證錯誤暫停的服務）。"""
        self._force = True
        self._wake.set()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="poller", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)

    # ---------------------------------------------------------------- 排程核心

    def tick(self) -> datetime:
        """輪詢所有到期的服務，回傳下一次需要醒來的時間。"""
        with self._lock:
            self._apply_pending()
            force, self._force = self._force, False
            for slot in self._slots:
                if force or slot.next_due <= self._clock.now():
                    self._service(slot, force=force)
            return min((s.next_due for s in self._slots), default=self._idle_until())

    def _idle_until(self) -> datetime:
        return self._clock.now() + timedelta(seconds=self._interval)

    def _service(self, slot: _Slot, *, force: bool) -> None:
        provider = slot.provider
        if slot.paused_signature is not None and not force:
            if self._signature(provider) == slot.paused_signature:
                slot.next_due = self._clock.now() + timedelta(seconds=AUTH_RECHECK_SECONDS)
                return
            log.info("%s 的憑證已改變，恢復輪詢", provider.id)
        slot.paused_signature = None

        try:
            usage = provider.poll()
        except PollError as e:
            self._on_error(slot, e)
        except Exception as e:  # 錯誤隔離：任何非預期例外只影響這個服務
            log.exception("%s 輪詢時發生未預期錯誤", provider.id)
            self._on_error(
                slot,
                PollError(
                    ErrKind.TRANSIENT,
                    f"未預期錯誤：{type(e).__name__}",
                    reason=ErrReason.UNEXPECTED,
                ),
            )
        else:
            self._on_success(slot, usage)

    def _on_success(self, slot: _Slot, usage: Usage) -> None:
        now = self._clock.now()
        slot.retries = 0
        slot.last_usage = usage
        slot.next_due = next_after_success(usage, now, self._interval)
        self._publish(slot, error=None)
        log.debug("%s 更新成功，下次 %s", slot.provider.id, slot.next_due.isoformat())

    def _on_error(self, slot: _Slot, error: PollError) -> None:
        now = self._clock.now()
        provider = slot.provider
        if error.kind is ErrKind.AUTH:
            slot.retries = 0
            slot.paused_signature = self._signature(provider)
            slot.next_due = now + timedelta(seconds=AUTH_RECHECK_SECONDS)
            log.warning("%s 認證錯誤，暫停輪詢直到憑證改變：%s", provider.id, error.message)
        else:
            slot.retries += 1
            delay = backoff_seconds(slot.retries, self._interval, error.retry_after)
            slot.next_due = now + timedelta(seconds=delay)
            log.warning(
                "%s 輪詢失敗（第 %d 次），%.0f 秒後重試：%s",
                provider.id,
                slot.retries,
                delay,
                error.message,
            )
        self._publish(slot, error=error)

    def _signature(self, provider: Provider) -> str:
        try:
            return provider.credential_signature()
        except Exception:
            log.exception("%s 取得憑證簽章失敗", provider.id)
            return ""

    def _publish(self, slot: _Slot, *, error: PollError | None) -> None:
        provider = slot.provider
        try:
            source = provider.source_label()
        except Exception:
            log.exception("%s 取得來源名稱失敗", provider.id)
            source = None
        self._store.update(
            ProviderState(
                provider_id=provider.id,
                usage=slot.last_usage,
                error=error,
                stale=error is not None and slot.last_usage is not None,
                source_label=source,
            )
        )

    # ---------------------------------------------------------------- 執行緒

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                wake_at = self.tick()
            except Exception:  # 理論上 tick 不會丟例外；保險起見不讓執行緒停掉
                log.exception("排程發生未預期錯誤")
                wake_at = self._clock.now() + timedelta(seconds=MIN_DELAY_SECONDS)
            timeout = max(0.0, (wake_at - self._clock.now()).total_seconds())
            self._wake.wait(timeout)
            self._wake.clear()
