"""ProviderState → 畫面要顯示的東西（純函式，不依賴 Qt）。

畫面程式碼只讀這裡產生的 VM，不對資料做任何假設；任何欄位缺漏都在這裡變成「—」。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, tzinfo
from enum import Enum

from usage_monitor.core import i18n, timefmt
from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.i18n import Lang, t
from usage_monitor.core.levels import Level, level_of
from usage_monitor.core.models import ProviderState, Usage, Window
from usage_monitor.services.update_check import UpdateState, UpdateStatus

SEGMENTS = 10
DEFAULT_LABELS = ("5h", "7d")
TOOLTIP_MAX = 127
EMPTY = "—"
UNREPORTED_TEXT = "0%"
SOON_SECONDS = 60
"""與 timefmt.countdown 相同：剩不到 60 秒就視為「即將重置」。"""


class RowStyle(Enum):
    NORMAL = "normal"
    STALE = "stale"
    """資料過期：進度條改暗色、文字變暗。"""
    ERROR = "error"
    """需要處理：進度條全灰、紅色「!」、文字「—」。"""
    EMPTY = "empty"
    """還沒有資料（讀取中）。"""


class NoteKind(Enum):
    ERROR = "error"
    MUTED = "muted"


@dataclass(frozen=True)
class RowVM:
    label: str
    filled: int
    level: Level | None
    text: str
    style: RowStyle


@dataclass(frozen=True)
class HoverLineVM:
    label: str
    """「5 小時」「7 天」"""
    percent: str
    level: Level | None
    detail: str


@dataclass(frozen=True)
class HoverVM:
    title: str
    source: str | None
    lines: tuple[HoverLineVM, ...]
    error: str | None
    updated: str | None
    hint: str = t(Lang.ZH_TW, "hover_hint")


@dataclass(frozen=True)
class ColumnVM:
    provider_id: str
    title: str
    note: str | None
    note_kind: NoteKind | None
    rows: tuple[RowVM, ...]
    hover: HoverVM


@dataclass(frozen=True)
class WidgetVM:
    columns: tuple[ColumnVM, ...]
    locked: bool = False


class Dot(Enum):
    RED = "red"
    """需要處理：找不到登入、登入過期、被拒絕。"""
    GRAY = "gray"
    """資料過期：暫時連不上。"""


@dataclass(frozen=True)
class TrayBar:
    percent: float
    level: Level


@dataclass(frozen=True)
class TrayVM:
    bars: tuple[TrayBar | None, TrayBar | None]
    dot: Dot | None
    tooltip: str
    update_dot: bool = False
    """右下角藍點：有新版本（與紅點、灰點不同位置，可同時出現）。"""


@dataclass(frozen=True)
class Notification:
    provider_id: str
    title: str
    body: str


ProviderInfo = tuple[str, str]
"""(provider_id, display_name)"""


# ---------------------------------------------------------------- 文字


def segments_for(percent: float) -> int:
    """42% → 4 格、18% → 2 格、6% → 1 格（只要用過就至少亮一格）、0% → 0 格。"""
    if percent <= 0:
        return 0
    return min(SEGMENTS, max(1, int(percent / 10 + 0.5)))


def percent_text(percent: float) -> str:
    return f"{int(percent + 0.5)}%"


def window_text(w: Window, now: datetime, tz: tzinfo | None = None, lang: Lang = Lang.ZH_TW) -> str:
    """「42% · 2時13分」「42% · 2h 13m」；已滿時「滿 · 20:15 重置」「Full · resets 20:15」。"""
    if not w.available:
        return EMPTY
    if w.percent >= 100:
        if w.resets_at is None:
            return t(lang, "full")
        return t(lang, "full_resets", time=timefmt.clock(w.resets_at, tz))
    if w.resets_at is None:
        return percent_text(w.percent)
    return f"{percent_text(w.percent)} · {timefmt.countdown(w.resets_at, now, lang)}"


def long_label(label: str, lang: Lang = Lang.ZH_TW) -> str:
    """ "5h" → 「5 小時」「5-hour」、"7d" → 「7 天」「7-day」。"""
    if label.endswith("h") and label[:-1].isdigit():
        return t(lang, "period_hours", n=label[:-1])
    if label.endswith("d") and label[:-1].isdigit():
        return t(lang, "period_days", n=label[:-1])
    return label


def source_text(source: str, lang: Lang = Lang.ZH_TW) -> str:
    """來源代碼 → 當前語言（「desktop」→「桌面版」）；不認得的代碼原樣顯示。"""
    key = f"source_{source}"
    return t(lang, key) if i18n.has(key) else source


def _reason(error: PollError) -> ErrReason | None:
    """舊程式或測試沒帶 reason 時，從 kind／status／訊息推回來。"""
    if error.reason is not None:
        return error.reason
    if error.kind is ErrKind.AUTH:
        if error.status in (401, 403):
            return ErrReason.REJECTED
        return ErrReason.EXPIRED if "過期" in error.message else ErrReason.NO_CREDENTIALS
    if error.kind is ErrKind.UNSUPPORTED:
        return ErrReason.UNSUPPORTED
    return None


def error_note(error: PollError, lang: Lang = Lang.ZH_TW) -> str:
    """欄名旁的短原因：未登入／已過期／被拒絕／不支援／連線失敗。"""
    key = {
        ErrReason.NO_CREDENTIALS: "note_not_signed_in",
        ErrReason.EXPIRED: "note_expired",
        ErrReason.REJECTED: "note_rejected",
        ErrReason.UNSUPPORTED: "note_unsupported",
    }.get(_reason(error), "note_offline")  # type: ignore[arg-type]
    return t(lang, key)


def error_detail(error: PollError, name: str, lang: Lang = Lang.ZH_TW) -> str:
    """完整的錯誤說明（懸停卡、設定視窗）。沒有 reason 時：中文顯示原訊息，英文顯示通用說明。"""
    reason = error.reason
    if reason is None:
        return error.message if lang is Lang.ZH_TW else t(lang, "error_unexpected")
    status = error.status if error.status is not None else "?"
    return t(lang, f"error_{reason.value}", name=name, status=status)


def needs_action(state: ProviderState) -> bool:
    """需要使用者處理（紅色）：認證錯誤，或從來沒成功過的錯誤。"""
    return state.error is not None and (state.error.kind is ErrKind.AUTH or state.usage is None)


# ---------------------------------------------------------------- 小工具


def _windows(usage: Usage | None) -> tuple[Window, Window]:
    if usage is None:
        return Window(label=DEFAULT_LABELS[0]), Window(label=DEFAULT_LABELS[1])
    return usage.session, usage.long


def _label(w: Window, index: int) -> str:
    return w.label or DEFAULT_LABELS[index]


def _row(
    w: Window, index: int, style: RowStyle, now: datetime, tz: tzinfo | None, lang: Lang
) -> RowVM:
    label = _label(w, index)
    if style is RowStyle.ERROR:
        return RowVM(label, 0, None, EMPTY, RowStyle.ERROR)
    if style is RowStyle.EMPTY:
        return RowVM(label, 0, None, EMPTY, RowStyle.EMPTY)
    if not w.available:
        # 服務沒有這個週期（例如 Codex 只有 30 天額度）：照樣畫空的計量條並顯示 0%
        return RowVM(label, 0, Level.OK, UNREPORTED_TEXT, style)
    return RowVM(
        label, segments_for(w.percent), level_of(w.percent), window_text(w, now, tz, lang), style
    )


def _hover(
    title: str, state: ProviderState | None, now: datetime, tz: tzinfo | None, lang: Lang
) -> HoverVM:
    hint = t(lang, "hover_hint")
    if state is None:
        return HoverVM(title, None, (), None, None, hint)
    lines: list[HoverLineVM] = []
    if state.usage is not None:
        for i, w in enumerate(_windows(state.usage)):
            period = long_label(_label(w, i), lang)
            if not w.available:
                detail = t(lang, "unreported_detail")
                lines.append(HoverLineVM(period, UNREPORTED_TEXT, None, detail))
                continue
            if w.resets_at is None:
                detail = t(lang, "hover_reset_unknown")
            elif (w.resets_at - now).total_seconds() < SOON_SECONDS:
                # 不到 1 分鐘時倒數會是「即將重置」，不能再套進「（…後）」
                detail = t(lang, "hover_reset_soon")
            else:
                detail = t(
                    lang,
                    "hover_reset_at",
                    moment=timefmt.reset_moment(w.resets_at, now, tz, lang),
                    countdown=timefmt.countdown(w.resets_at, now, lang),
                )
            lines.append(HoverLineVM(period, percent_text(w.percent), level_of(w.percent), detail))
    updated = None
    if state.usage is not None:
        time = timefmt.clock(state.usage.fetched_at, tz)
        if state.stale:
            ago = timefmt.ago(state.usage.fetched_at, now, lang)
            updated = t(lang, "hover_updated_ago", time=time, ago=ago)
        else:
            updated = t(lang, "hover_updated", time=time)
    source = state.source_label
    return HoverVM(
        title=title,
        source=t(lang, "hover_source", source=source_text(source, lang)) if source else None,
        lines=tuple(lines),
        error=error_detail(state.error, title, lang) if state.error else None,
        updated=updated,
        hint=hint,
    )


def build_column(
    provider: ProviderInfo,
    state: ProviderState | None,
    now: datetime,
    tz: tzinfo | None = None,
    lang: Lang = Lang.ZH_TW,
) -> ColumnVM:
    pid, title = provider
    hover = _hover(title, state, now, tz, lang)

    def rows(windows: tuple[Window, Window], style: RowStyle) -> tuple[RowVM, ...]:
        return tuple(_row(w, i, style, now, tz, lang) for i, w in enumerate(windows))

    if state is None:
        return ColumnVM(
            pid, title, t(lang, "loading"), NoteKind.MUTED, rows(_windows(None), RowStyle.EMPTY),
            hover,
        )  # fmt: skip

    windows = _windows(state.usage)
    if needs_action(state):
        assert state.error is not None
        note = error_note(state.error, lang)
        return ColumnVM(pid, title, note, NoteKind.ERROR, rows(windows, RowStyle.ERROR), hover)

    if state.stale and state.usage is not None:
        note = timefmt.ago(state.usage.fetched_at, now, lang)
        return ColumnVM(pid, title, note, NoteKind.MUTED, rows(windows, RowStyle.STALE), hover)

    return ColumnVM(pid, title, None, None, rows(windows, RowStyle.NORMAL), hover)


def build_widget_vm(
    providers: Sequence[ProviderInfo],
    states: Mapping[str, ProviderState],
    now: datetime,
    *,
    locked: bool = False,
    tz: tzinfo | None = None,
    lang: Lang = Lang.ZH_TW,
) -> WidgetVM:
    """只為已啟用的服務產生欄位；沒有啟用任何服務時欄位為空。"""
    columns = tuple(build_column(p, states.get(p[0]), now, tz, lang) for p in providers)
    return WidgetVM(columns=columns, locked=locked)


# ---------------------------------------------------------------- 系統匣


def _tooltip_line(column: ColumnVM, state: ProviderState | None, lang: Lang) -> str:
    if state is None or state.usage is None or needs_action(state):
        return t(lang, "tray_error_line", name=column.title, note=column.note or EMPTY)
    stale = t(lang, "tray_stale") if state.stale else ""
    parts = " | ".join(f"{row.label} {row.text}" for row in column.rows)
    return f"{column.title}{stale} {parts}"


def truncate(text: str, limit: int = TOOLTIP_MAX) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_tray_vm(
    providers: Sequence[ProviderInfo],
    states: Mapping[str, ProviderState],
    now: datetime,
    tz: tzinfo | None = None,
    lang: Lang = Lang.ZH_TW,
    update_available: bool = False,
) -> TrayVM:
    """圖示畫第一個服務（Claude）的兩個週期；提示文字每個服務一行，最多 127 字元。"""
    lines: list[str] = []
    for p in providers:
        state = states.get(p[0])
        lines.append(_tooltip_line(build_column(p, state, now, tz, lang), state, lang))

    bars: tuple[TrayBar | None, TrayBar | None] = (None, None)
    if providers:
        first = states.get(providers[0][0])
        if first is not None and first.usage is not None and not needs_action(first):
            s, lw = first.usage.session, first.usage.long
            bars = (
                TrayBar(s.percent, level_of(s.percent)) if s.available else None,
                TrayBar(lw.percent, level_of(lw.percent)) if lw.available else None,
            )

    active = [states[p[0]] for p in providers if p[0] in states]
    dot: Dot | None = None
    if any(needs_action(s) for s in active):
        dot = Dot.RED
    elif any(s.stale for s in active):
        dot = Dot.GRAY
    return TrayVM(
        bars=bars,
        dot=dot,
        tooltip=truncate("\n".join(lines) or t(lang, "tray_none")),
        update_dot=update_available,
    )


# ---------------------------------------------------------------- 更新檢查


def update_status_text(state: UpdateState | None, lang: Lang = Lang.ZH_TW) -> str:
    """「關於」頁版本下方那一行。"""
    if state is None:
        return t(lang, "update_status_unknown")
    version = state.latest_version or ""
    if state.status is UpdateStatus.AVAILABLE:
        key = "update_status_skipped" if state.skipped else "update_status_available"
        return t(lang, key, version=version)
    key = {
        UpdateStatus.CHECKING: "update_status_checking",
        UpdateStatus.UP_TO_DATE: "update_status_up_to_date",
        UpdateStatus.UNAVAILABLE: "update_status_unavailable",
    }.get(state.status, "update_status_unknown")
    return t(lang, key)


def update_menu_text(state: UpdateState | None, lang: Lang = Lang.ZH_TW) -> str | None:
    """系統匣選單最上面那一行；沒有要提醒的新版時回傳 None。"""
    if state is None or not state.should_alert or state.latest_version is None:
        return None
    return t(lang, "update_menu", version=state.latest_version)


# ---------------------------------------------------------------- 設定視窗


class StatusKind(Enum):
    OK = "ok"
    ERROR = "error"
    MUTED = "muted"


@dataclass(frozen=True)
class ServiceStatusVM:
    text: str
    kind: StatusKind


def service_status(
    enabled: bool,
    state: ProviderState | None,
    now: datetime,
    lang: Lang = Lang.ZH_TW,
    name: str = "",
) -> ServiceStatusVM:
    """設定視窗「服務」區每個服務底下那一行（畫板 5：「已連線 · 來源：Claude 桌面版」）。"""
    if not enabled:
        return ServiceStatusVM(t(lang, "status_disabled"), StatusKind.MUTED)
    if state is None:
        return ServiceStatusVM(t(lang, "loading"), StatusKind.MUTED)
    if needs_action(state):
        assert state.error is not None
        text = t(
            lang,
            "status_error",
            note=error_note(state.error, lang),
            detail=error_detail(state.error, name or state.provider_id, lang),
        )
        return ServiceStatusVM(text, StatusKind.ERROR)
    if state.stale and state.usage is not None:
        ago = timefmt.ago(state.usage.fetched_at, now, lang)
        return ServiceStatusVM(t(lang, "status_stale", ago=ago), StatusKind.MUTED)
    if state.source_label:
        source = source_text(state.source_label, lang)
        return ServiceStatusVM(t(lang, "status_connected_source", source=source), StatusKind.OK)
    return ServiceStatusVM(t(lang, "status_connected"), StatusKind.OK)


# ---------------------------------------------------------------- 通知


class AuthNotifier:
    """認證錯誤只通知一次；錯誤消失後重置，下次再出錯會再通知。網路錯誤不通知。"""

    def __init__(self) -> None:
        self._notified: set[str] = set()

    def update(
        self,
        providers: Sequence[ProviderInfo],
        states: Mapping[str, ProviderState],
        lang: Lang = Lang.ZH_TW,
    ) -> list[Notification]:
        result: list[Notification] = []
        for pid, name in providers:
            state = states.get(pid)
            error = state.error if state else None
            if error is None or error.kind is not ErrKind.AUTH:
                self._notified.discard(pid)
                continue
            if pid in self._notified:
                continue
            self._notified.add(pid)
            key = {
                ErrReason.NO_CREDENTIALS: "notify_not_signed_in",
                ErrReason.EXPIRED: "notify_expired",
            }.get(_reason(error), "notify_rejected")  # type: ignore[arg-type]
            result.append(
                Notification(pid, t(lang, key, name=name), t(lang, "notify_body", name=name))
            )
        return result
