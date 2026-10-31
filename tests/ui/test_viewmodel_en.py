"""ViewModel 英文版黃金測試（CLAUDE.md §3.8）：同樣的 ProviderState，lang=EN 時的預期輸出。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.i18n import Lang
from usage_monitor.core.levels import Level
from usage_monitor.core.models import ProviderState, Usage, Window
from usage_monitor.ui.viewmodel import (
    AuthNotifier,
    HoverLineVM,
    HoverVM,
    NoteKind,
    RowStyle,
    RowVM,
    ServiceStatusVM,
    StatusKind,
    build_tray_vm,
    build_widget_vm,
    error_detail,
    error_note,
    long_label,
    service_status,
    source_text,
    window_text,
)

EN = Lang.EN
TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 29, 10, 7, tzinfo=UTC)  # 台北 18:07（週四）
H, M, D = timedelta(hours=1), timedelta(minutes=1), timedelta(days=1)
CLAUDE = ("claude", "Claude")
CODEX = ("codex", "Codex")


def win(percent: float, resets_in: timedelta | None, label: str) -> Window:
    return Window(True, percent, NOW + resets_in if resets_in else None, label)


def ok(pid: str, u: Usage, source: str | None = "desktop") -> ProviderState:
    return ProviderState(pid, u, None, False, source)


def auth(pid: str, reason: ErrReason, status: int | None = None) -> ProviderState:
    return ProviderState(pid, None, PollError(ErrKind.AUTH, "中文訊息", reason=reason,
                                              status=status), False, None)  # fmt: skip


def test_normal_rows() -> None:
    u = Usage(win(42, 2 * H + 13 * M, "5h"), win(18, 4 * D + 3 * H, "7d"), NOW)
    (column,) = build_widget_vm([CLAUDE], {"claude": ok("claude", u)}, NOW, lang=EN).columns
    assert column.rows == (
        RowVM("5h", 4, Level.OK, "42% · 2h 13m", RowStyle.NORMAL),
        RowVM("7d", 2, Level.OK, "18% · 4d 3h", RowStyle.NORMAL),
    )


def test_full_and_month() -> None:
    full = Window(True, 100, datetime(2026, 10, 29, 12, 15, tzinfo=UTC), "5h")
    assert window_text(full, NOW, TPE, EN) == "Full · resets 20:15"
    assert window_text(Window(True, 100), NOW, TPE, EN) == "Full"
    assert window_text(win(6, 29 * D + H, "30d"), NOW, TPE, EN) == "6% · 29d"


@pytest.mark.parametrize(
    ("reason", "status", "note"),
    [
        (ErrReason.NO_CREDENTIALS, None, "Not signed in"),
        (ErrReason.EXPIRED, None, "Expired"),
        (ErrReason.REJECTED, 401, "Rejected"),
    ],
)
def test_auth_notes(reason: ErrReason, status: int | None, note: str) -> None:
    (column,) = build_widget_vm([CLAUDE], {"claude": auth("claude", reason, status)}, NOW,
                                lang=EN).columns  # fmt: skip
    assert (column.note, column.note_kind) == (note, NoteKind.ERROR)
    assert column.rows[0] == RowVM("5h", 0, None, "—", RowStyle.ERROR)


def test_loading_and_stale_notes() -> None:
    (loading,) = build_widget_vm([CLAUDE], {}, NOW, lang=EN).columns
    assert loading.note == "Loading…"
    u = Usage(win(42, 2 * H, "5h"), win(18, D, "7d"), NOW - 12 * M)
    stale = ProviderState("claude", u, PollError(ErrKind.TRANSIENT, "x"), True, "desktop")
    (column,) = build_widget_vm([CLAUDE], {"claude": stale}, NOW, lang=EN).columns
    assert column.note == "12 min ago"


def test_hover_card() -> None:
    u = Usage(
        Window(True, 42, datetime(2026, 10, 29, 12, 20, tzinfo=UTC), "5h"),
        Window(label="30d"),
        datetime(2026, 10, 29, 10, 5, tzinfo=UTC),
    )
    (column,) = build_widget_vm([CODEX], {"codex": ok("codex", u, "codex_cli")}, NOW, tz=TPE,
                                lang=EN).columns  # fmt: skip
    assert column.hover == HoverVM(
        title="Codex",
        source="Source: Codex CLI",
        lines=(
            HoverLineVM("5-hour", "42%", Level.OK, "Resets today 20:20 (in 2h 13m)"),
            HoverLineVM("30-day", "0%", None, "Not reported for this plan"),
        ),
        error=None,
        updated="Updated 18:05",
        hint="Double-click to refresh",
    )


@pytest.mark.parametrize(("lang", "text"), [(EN, "Resets soon"), (Lang.ZH_TW, "即將重置")])
def test_hover_reset_within_a_minute_says_soon(lang: Lang, text: str) -> None:
    """2026-10-30 bug：剩不到 1 分鐘時懸停卡顯示「Resets today 00:50 (in soon)」。"""
    u = Usage(win(38, timedelta(seconds=30), "5h"), win(1, D, "7d"), NOW)
    (column,) = build_widget_vm([CLAUDE], {"claude": ok("claude", u)}, NOW, lang=lang).columns
    assert column.hover.lines[0].detail == text


def test_tray_tooltip() -> None:
    u = Usage(win(42, 2 * H + 13 * M, "5h"), win(18, 4 * D + 3 * H, "7d"), NOW)
    tray = build_tray_vm(
        [CLAUDE, CODEX], {"claude": ok("claude", u), "codex": auth("codex", ErrReason.EXPIRED)},
        NOW, lang=EN,
    )  # fmt: skip
    assert tray.tooltip == "Claude 5h 42% · 2h 13m | 7d 18% · 4d 3h\nCodex: Expired"
    assert build_tray_vm([], {}, NOW, lang=EN).tooltip == "No services enabled"


def test_tray_stale_marker() -> None:
    u = Usage(win(42, None, "5h"), win(18, None, "7d"), NOW - M)
    state = ProviderState("claude", u, PollError(ErrKind.TRANSIENT, "x"), True, None)
    assert build_tray_vm([CLAUDE], {"claude": state}, NOW, lang=EN).tooltip.startswith(
        "Claude (stale) 5h 42%"
    )


@pytest.mark.parametrize(
    ("enabled", "state", "text", "kind"),
    [
        (False, None, "Disabled", StatusKind.MUTED),
        (True, None, "Loading…", StatusKind.MUTED),
        (True, ok("claude", Usage(Window(), Window(), NOW)), "Connected · Source: Desktop app",
         StatusKind.OK),
        (True, ok("claude", Usage(Window(), Window(), NOW), None), "Connected", StatusKind.OK),
        (True, auth("claude", ErrReason.NO_CREDENTIALS), "Not signed in · No Claude sign-in found",
         StatusKind.ERROR),
        (True, ProviderState("claude", Usage(Window(), Window(), NOW - 12 * M),
                             PollError(ErrKind.TRANSIENT, "x"), True, None),
         "Temporarily offline · showing data from 12 min ago", StatusKind.MUTED),
    ],
)  # fmt: skip
def test_service_status(
    enabled: bool, state: ProviderState | None, text: str, kind: StatusKind
) -> None:
    assert service_status(enabled, state, NOW, EN, "Claude") == ServiceStatusVM(text, kind)


@pytest.mark.parametrize(
    ("reason", "status", "text"),
    [
        (ErrReason.NO_CREDENTIALS, None, "No Claude sign-in found"),
        (ErrReason.EXPIRED, None, "Claude sign-in has expired"),
        (ErrReason.REJECTED, 403, "Sign-in rejected (HTTP 403)"),
        (ErrReason.RATE_LIMITED, 429, "Rate limited; retrying automatically"),
        (ErrReason.SERVER, 503, "Server unavailable (HTTP 503)"),
        (ErrReason.NETWORK, None, "Can't connect"),
        (ErrReason.TIMEOUT, None, "Connection timed out"),
        (ErrReason.UNSUPPORTED, None, "Usage API not supported for this account (HTTP ?)"),
        (ErrReason.BAD_RESPONSE, None, "Unrecognized response"),
        (ErrReason.UNEXPECTED, None, "Unexpected error"),
    ],
)
def test_error_detail_every_reason(reason: ErrReason, status: int | None, text: str) -> None:
    error = PollError(ErrKind.TRANSIENT, "中文 log 訊息", reason=reason, status=status)
    assert error_detail(error, "Claude", EN) == text


def test_error_without_reason() -> None:
    """舊程式或測試沒帶 reason：中文顯示原訊息，英文顯示通用說明，短原因由 kind／status 推回。"""
    error = PollError(ErrKind.AUTH, "找不到登入", status=None)
    assert error_detail(error, "Claude", Lang.ZH_TW) == "找不到登入"
    assert error_detail(error, "Claude", EN) == "Unexpected error"
    assert error_note(error, EN) == "Not signed in"
    assert error_note(PollError(ErrKind.TRANSIENT, "x"), EN) == "Offline"
    assert error_note(PollError(ErrKind.UNSUPPORTED, "x"), EN) == "Unsupported"


def test_notifications() -> None:
    n = AuthNotifier()
    (first,) = n.update([CLAUDE], {"claude": auth("claude", ErrReason.NO_CREDENTIALS)}, EN)
    assert first.title == "Claude: not signed in"
    assert first.body.startswith("Open Claude and make sure you're signed in.")
    (expired,) = AuthNotifier().update([CLAUDE], {"claude": auth("claude", ErrReason.EXPIRED)}, EN)
    assert expired.title == "Claude: sign-in expired"
    (rejected,) = AuthNotifier().update(
        [CLAUDE], {"claude": auth("claude", ErrReason.REJECTED, 401)}, EN
    )
    assert rejected.title == "Claude: sign-in rejected"


def test_labels_and_sources() -> None:
    assert (long_label("5h", EN), long_label("7d", EN), long_label("30d", EN)) == (
        "5-hour",
        "7-day",
        "30-day",
    )
    assert source_text("desktop", EN) == "Desktop app"
    assert source_text("desktop") == "桌面版"
    assert source_text("unknown-src", EN) == "unknown-src"
