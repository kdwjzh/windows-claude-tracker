"""ViewModel 黃金測試：設計稿畫板 2 的每一種狀態，輸入固定的 ProviderState，比對預期 VM。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from usage_monitor.core.errors import ErrKind, PollError
from usage_monitor.core.levels import Level
from usage_monitor.core.models import ProviderState, Usage, Window
from usage_monitor.ui.viewmodel import (
    AuthNotifier,
    ColumnVM,
    Dot,
    HoverLineVM,
    HoverVM,
    NoteKind,
    RecentUse,
    RowStyle,
    RowVM,
    ServiceStatusVM,
    StatusKind,
    TrayBar,
    build_tray_vm,
    build_widget_vm,
    long_label,
    segments_for,
    service_status,
    truncate,
    window_text,
)

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 29, 10, 7, tzinfo=UTC)  # 台北 18:07
CLAUDE = ("claude", "Claude")
CODEX = ("codex", "Codex")
BOTH = [CLAUDE, CODEX]


def win(percent: float, resets_in: timedelta | None, label: str) -> Window:
    return Window(True, percent, NOW + resets_in if resets_in else None, label)


def usage(
    s: float,
    s_in: timedelta,
    lw: float,
    l_in: timedelta,
    long_label: str = "7d",
    fetched: datetime | None = None,
) -> Usage:
    at = fetched or NOW - timedelta(minutes=2)
    return Usage(win(s, s_in, "5h"), win(lw, l_in, long_label), at)


def ok(pid: str, u: Usage, source: str = "桌面版") -> ProviderState:
    return ProviderState(pid, usage=u, error=None, stale=False, source_label=source)


H = timedelta(hours=1)
M = timedelta(minutes=1)
D = timedelta(days=1)

CLAUDE_NORMAL = usage(42, 2 * H + 13 * M, 18, 4 * D + 3 * H)
CODEX_NORMAL = usage(12, 3 * H + 40 * M, 6, 29 * D + 5 * H, long_label="30d")


def vm(states: dict[str, ProviderState], providers=BOTH, locked: bool = False):  # type: ignore[no-untyped-def]
    return build_widget_vm(providers, states, NOW, locked=locked, tz=TPE)


# ---------------------------------------------------------------- 畫板 2 的 8 種狀態


def test_state_1_normal_two_services() -> None:
    result = vm({"claude": ok("claude", CLAUDE_NORMAL), "codex": ok("codex", CODEX_NORMAL, "CLI")})
    claude, codex = result.columns
    assert claude.title == "Claude" and claude.note is None
    assert claude.rows == (
        RowVM("5h", 4.2, Level.OK, "42% · 2時13分", RowStyle.NORMAL),
        RowVM("7d", 1.8, Level.OK, "18% · 4天3時", RowStyle.NORMAL),
    )
    assert codex.rows == (
        RowVM("5h", 1.2, Level.OK, "12% · 3時40分", RowStyle.NORMAL),
        RowVM("30d", 0.6, Level.OK, "6% · 29天", RowStyle.NORMAL),  # 依實際週期，不寫死 7d
    )


def test_state_2_near_limit() -> None:
    u = usage(78, 48 * M, 93, 1 * D + 2 * H)
    (column,) = vm({"claude": ok("claude", u)}, [CLAUDE]).columns
    assert column.rows == (
        RowVM("5h", 7.8, Level.WARN, "78% · 48分", RowStyle.NORMAL),
        RowVM("7d", 9.3, Level.CRIT, "93% · 1天2時", RowStyle.NORMAL),
    )


def test_state_3_full_shows_local_reset_time() -> None:
    u = Usage(
        Window(True, 100, datetime(2026, 10, 29, 12, 15, tzinfo=UTC), "5h"),
        win(64, 3 * D + 5 * H, "7d"),
        NOW,
    )
    (column,) = vm({"claude": ok("claude", u)}, [CLAUDE]).columns
    assert column.rows[0] == RowVM("5h", 10, Level.CRIT, "滿 · 20:15 重置", RowStyle.NORMAL)
    assert column.rows[1] == RowVM("7d", 6.4, Level.OK, "64% · 3天5時", RowStyle.NORMAL)


def test_state_4_not_logged_in_other_column_unaffected() -> None:
    claude = ProviderState(
        "claude",
        usage=None,
        error=PollError(ErrKind.AUTH, "找不到 Claude 登入資訊"),
        stale=False,
        source_label=None,
    )
    result = vm({"claude": claude, "codex": ok("codex", CODEX_NORMAL)})
    c, x = result.columns
    assert (c.note, c.note_kind) == ("未登入", NoteKind.ERROR)
    assert c.rows == (
        RowVM("5h", 0, None, "—", RowStyle.ERROR),
        RowVM("7d", 0, None, "—", RowStyle.ERROR),
    )
    assert x.note is None and x.rows[0].style is RowStyle.NORMAL


def test_state_5_stale_dims_and_shows_age() -> None:
    u = Usage(win(42, 2 * H + 1 * M, "5h"), win(18, 4 * D + 3 * H, "7d"), NOW - 12 * M)
    state = ProviderState(
        "claude", usage=u, error=PollError(ErrKind.TRANSIENT, "連線逾時"), stale=True,
        source_label="桌面版",
    )  # fmt: skip
    (column,) = vm({"claude": state}, [CLAUDE]).columns
    assert (column.note, column.note_kind) == ("12 分鐘前", NoteKind.MUTED)
    assert [r.style for r in column.rows] == [RowStyle.STALE, RowStyle.STALE]
    assert column.rows[0].text == "42% · 2時01分"


def test_state_6_only_one_service_has_one_column() -> None:
    result = vm(
        {"claude": ok("claude", CLAUDE_NORMAL), "codex": ok("codex", CODEX_NORMAL)}, [CLAUDE]
    )
    assert [c.provider_id for c in result.columns] == ["claude"]


def test_state_7_locked_flag() -> None:
    assert vm({}, locked=True).locked is True
    assert vm({}).locked is False


def test_state_8_light_theme_uses_same_vm() -> None:
    """淺色主題只換顏色（theme.LIGHT），VM 不變。"""
    from usage_monitor.ui import theme

    states = {"claude": ok("claude", CLAUDE_NORMAL)}
    assert vm(states) == vm(states)
    assert theme.LIGHT.bg == "#f3f3f3" and theme.DARK.bg == "#232428"


# ---------------------------------------------------------------- 其他狀態


def test_loading_before_first_result() -> None:
    (column,) = vm({}, [CLAUDE]).columns
    assert (column.note, column.note_kind) == ("讀取中…", NoteKind.MUTED)
    assert column.rows == (
        RowVM("5h", 0, None, "—", RowStyle.EMPTY),
        RowVM("7d", 0, None, "—", RowStyle.EMPTY),
    )


def test_auth_error_with_old_usage_still_needs_action() -> None:
    state = ProviderState(
        "claude", usage=CLAUDE_NORMAL, error=PollError(ErrKind.AUTH, "登入被拒絕", status=401),
        stale=True, source_label="桌面版",
    )  # fmt: skip
    (column,) = vm({"claude": state}, [CLAUDE]).columns
    assert column.note == "被拒絕"
    assert column.rows[0] == RowVM("5h", 0, None, "—", RowStyle.ERROR)


@pytest.mark.parametrize(
    ("error", "note"),
    [
        (PollError(ErrKind.AUTH, "Claude 登入已過期（來源：CLI）"), "已過期"),
        (PollError(ErrKind.TRANSIENT, "連線逾時"), "連線失敗"),
        (PollError(ErrKind.UNSUPPORTED, "不支援", status=404), "不支援"),
    ],
)
def test_error_without_usage_notes(error: PollError, note: str) -> None:
    state = ProviderState("claude", usage=None, error=error, stale=False, source_label=None)
    (column,) = vm({"claude": state}, [CLAUDE]).columns
    assert (column.note, column.note_kind) == (note, NoteKind.ERROR)


def test_unreported_window_shows_empty_bar_and_zero() -> None:
    """服務沒回報的週期（例如 Codex 只有 30 天額度）：照樣畫空計量條並顯示 0%。"""
    u = Usage(Window(label="5h"), win(32, 29 * D + H, "30d"), NOW)
    (column,) = vm({"codex": ok("codex", u, "Codex CLI")}, [CODEX]).columns
    assert column.rows == (
        RowVM("5h", 0, Level.OK, "0%", RowStyle.NORMAL),
        RowVM("30d", 3.2, Level.OK, "32% · 29天", RowStyle.NORMAL),
    )


def test_unreported_window_follows_stale_style() -> None:
    u = Usage(Window(label="5h"), win(32, 29 * D, "30d"), NOW - 12 * M)
    state = ProviderState(
        "codex", usage=u, error=PollError(ErrKind.TRANSIENT, "x"), stale=True, source_label=None
    )
    (column,) = vm({"codex": state}, [CODEX]).columns
    assert column.rows[0] == RowVM("5h", 0, Level.OK, "0%", RowStyle.STALE)


def test_missing_labels_use_defaults() -> None:
    u = Usage(Window(True, 10), Window(True, 20), NOW)
    (column,) = vm({"claude": ok("claude", u)}, [CLAUDE]).columns
    assert [r.label for r in column.rows] == ["5h", "7d"]
    assert column.rows[0].text == "10%"


# ---------------------------------------------------------------- 文字規則


@pytest.mark.parametrize(
    ("percent", "filled"),
    [(0, 0), (0.4, 0), (1, 0.1), (6, 0.6), (12, 1.2), (15, 1.5), (18, 1.8), (41.6, 4.2),
     (42, 4.2), (78, 7.8), (93, 9.3), (100, 10), (130, 10), (-5, 0)],
)  # fmt: skip
def test_segments_for(percent: float, filled: float) -> None:
    """2026-11-02 改成連續填滿：每 1% 是一格的 1/10（原本 1–14% 都算一整格）。"""
    assert segments_for(percent) == filled


def test_window_text_variants() -> None:
    assert window_text(Window(), NOW) == "—"
    assert window_text(Window(True, 100), NOW) == "滿"
    assert window_text(Window(True, 41.6), NOW) == "42%"


@pytest.mark.parametrize(
    ("label", "text"),
    [("5h", "5 小時"), ("7d", "7 天"), ("30d", "30 天"), ("x", "x"), ("hd", "hd")],
)
def test_long_label(label: str, text: str) -> None:
    assert long_label(label) == text


# ---------------------------------------------------------------- 懸停卡


def test_hover_card_details() -> None:
    u = Usage(
        Window(True, 42, datetime(2026, 10, 29, 12, 20, tzinfo=UTC), "5h"),
        Window(True, 18, datetime(2026, 11, 1, 14, 0, tzinfo=UTC), "7d"),
        datetime(2026, 10, 29, 10, 5, tzinfo=UTC),
    )
    (column,) = vm({"claude": ok("claude", u)}, [CLAUDE]).columns
    assert column.hover == HoverVM(
        title="Claude",
        source="來源：桌面版",
        lines=(
            HoverLineVM("5 小時", "42%", Level.OK, "今天 20:20 重置（2時13分後）"),
            HoverLineVM("7 天", "18%", Level.OK, "11/01（日）22:00 重置（3天3時後）"),
        ),
        error=None,
        updated="最後更新 18:05",
    )


def test_hover_card_stale_error_and_missing() -> None:
    u = Usage(Window(True, 42, None, "5h"), Window(label="7d"), NOW - 12 * M)
    state = ProviderState(
        "claude", usage=u, error=PollError(ErrKind.TRANSIENT, "連線逾時"), stale=True,
        source_label=None,
    )  # fmt: skip
    hover = vm({"claude": state}, [CLAUDE]).columns[0].hover
    assert hover.source is None
    assert hover.lines == (
        HoverLineVM("5 小時", "42%", Level.OK, "重置時間未知"),
        HoverLineVM("7 天", "0%", None, "這個方案沒有回報此週期"),
    )
    assert hover.error == "連線逾時"
    assert hover.updated == "最後更新 17:55（12 分鐘前）"


def test_hover_card_reset_in_past() -> None:
    u = Usage(Window(True, 42, NOW - M, "5h"), Window(True, 1, None, "7d"), NOW)
    hover = vm({"claude": ok("claude", u)}, [CLAUDE]).columns[0].hover
    # 重置時間已過：不再說「即將重置」，舊百分比也不再顯示（ROADMAP 第 2 項）
    assert hover.lines[0] == HoverLineVM("5 小時", "0%", Level.OK, "已重置 · 更新中")


def test_hover_card_loading() -> None:
    assert vm({}, [CLAUDE]).columns[0].hover == HoverVM("Claude", None, (), None, None)


# ---------------------------------------------------------------- 系統匣


def test_tray_normal() -> None:
    tray = build_tray_vm(
        BOTH, {"claude": ok("claude", CLAUDE_NORMAL), "codex": ok("codex", CODEX_NORMAL)}, NOW, TPE
    )
    assert tray.bars == (TrayBar(42, Level.OK), TrayBar(18, Level.OK))
    assert tray.dot is None
    assert tray.tooltip == (
        "Claude 5h 42% · 2時13分 | 7d 18% · 4天3時\nCodex 5h 12% · 3時40分 | 30d 6% · 29天"
    )


def test_tray_auth_error_red_dot() -> None:
    claude = ProviderState(
        "claude", usage=None, error=PollError(ErrKind.AUTH, "找不到"), stale=False,
        source_label=None,
    )  # fmt: skip
    tray = build_tray_vm(BOTH, {"claude": claude, "codex": ok("codex", CODEX_NORMAL)}, NOW, TPE)
    assert tray.bars == (None, None)
    assert tray.dot is Dot.RED
    assert tray.tooltip.splitlines()[0] == "Claude：未登入"


def test_tray_stale_gray_dot_and_marker() -> None:
    state = ProviderState(
        "claude", usage=CLAUDE_NORMAL, error=PollError(ErrKind.TRANSIENT, "x"), stale=True,
        source_label=None,
    )  # fmt: skip
    tray = build_tray_vm([CLAUDE], {"claude": state}, NOW, TPE)
    assert tray.dot is Dot.GRAY
    assert tray.tooltip.startswith("Claude(舊) 5h 42%")
    assert tray.bars[0] == TrayBar(42, Level.OK)


def test_tray_loading_and_no_providers() -> None:
    assert build_tray_vm([CLAUDE], {}, NOW).tooltip == "Claude：讀取中…"
    assert build_tray_vm([], {}, NOW).tooltip == "沒有啟用任何服務"


def test_tray_unavailable_window_has_no_bar() -> None:
    u = Usage(win(42, 2 * H, "5h"), Window(label="7d"), NOW)
    tray = build_tray_vm([CLAUDE], {"claude": ok("claude", u)}, NOW)
    assert tray.bars == (TrayBar(42, Level.OK), None)  # 圖示上就是一條空的軌道
    assert tray.tooltip == "Claude 5h 42% · 2時00分 | 7d 0%"


def test_tooltip_truncated_to_127() -> None:
    providers = [(f"p{i}", "很長的服務名稱" * 3) for i in range(5)]
    tooltip = build_tray_vm(providers, {}, NOW).tooltip
    assert len(tooltip) == 127
    assert tooltip.endswith("…")
    assert truncate("short") == "short"


# ---------------------------------------------------------------- 設定視窗的服務狀態


@pytest.mark.parametrize(
    ("enabled", "state", "text", "kind"),
    [
        (False, None, "已停用", StatusKind.MUTED),
        (True, None, "讀取中…", StatusKind.MUTED),
        (True, ok("claude", CLAUDE_NORMAL), "已連線 · 來源：桌面版", StatusKind.OK),
        (
            True,
            ProviderState("codex", CODEX_NORMAL, None, False, None),
            "已連線",
            StatusKind.OK,
        ),
        (
            True,
            ProviderState("claude", None, PollError(ErrKind.AUTH, "找不到 Claude 登入資訊"), False,
                          None),
            "未登入 · 找不到 Claude 登入資訊",
            StatusKind.ERROR,
        ),
        (
            True,
            ProviderState(
                "claude", Usage(CLAUDE_NORMAL.session, CLAUDE_NORMAL.long, NOW - 12 * M),
                PollError(ErrKind.TRANSIENT, "連線逾時"), True, "桌面版",
            ),
            "暫時連不上 · 顯示 12 分鐘前的資料",
            StatusKind.MUTED,
        ),
    ],
)  # fmt: skip
def test_service_status(
    enabled: bool, state: ProviderState | None, text: str, kind: StatusKind
) -> None:
    assert service_status(enabled, state, NOW) == ServiceStatusVM(text, kind)


# ---------------------------------------------------------------- 通知


def _auth(pid: str, message: str = "找不到登入資訊", status: int | None = None) -> ProviderState:
    return ProviderState(
        pid, usage=None, error=PollError(ErrKind.AUTH, message, status=status), stale=False,
        source_label=None,
    )  # fmt: skip


def test_auth_notified_once_and_reset_after_recovery() -> None:
    n = AuthNotifier()
    first = n.update([CLAUDE], {"claude": _auth("claude")})
    assert [x.title for x in first] == ["Claude 找不到登入資訊"]
    assert "不需要重開本程式" in first[0].body
    assert n.update([CLAUDE], {"claude": _auth("claude")}) == []
    assert n.update([CLAUDE], {"claude": ok("claude", CLAUDE_NORMAL)}) == []
    assert len(n.update([CLAUDE], {"claude": _auth("claude")})) == 1


@pytest.mark.parametrize(
    ("state", "title"),
    [
        (_auth("claude", "Claude 登入已過期（來源：CLI）"), "Claude 登入已過期"),
        (_auth("claude", "被拒", status=403), "Claude 登入被拒絕"),
    ],
)
def test_auth_notification_titles(state: ProviderState, title: str) -> None:
    assert AuthNotifier().update([CLAUDE], {"claude": state})[0].title == title


def test_transient_errors_do_not_notify() -> None:
    state = ProviderState(
        "claude", usage=None, error=PollError(ErrKind.TRANSIENT, "x"), stale=False,
        source_label=None,
    )  # fmt: skip
    assert AuthNotifier().update([CLAUDE], {"claude": state}) == []
    assert AuthNotifier().update([CLAUDE], {}) == []


def test_columns_are_independent_objects() -> None:
    result = vm({"claude": ok("claude", CLAUDE_NORMAL)})
    assert isinstance(result.columns[0], ColumnVM)
    assert result.columns[1].note == "讀取中…"


# ---------------------------------------------------------------- 重置時間已過（睡眠喚醒）


def test_reset_passed_clears_bar_until_next_poll() -> None:
    """前一晚的「5h 100%」在重置時間過後不能繼續亮紅色（ROADMAP 第 2 項）。"""
    u = usage(100, -8 * H, 64, 3 * D + 5 * H)
    state = ok("claude", u)
    (column,) = vm({"claude": state}, [CLAUDE]).columns
    assert column.rows[0] == RowVM("5h", 0, Level.OK, "已重置 · 更新中", RowStyle.NORMAL)
    assert column.rows[1] == RowVM("7d", 6.4, Level.OK, "64% · 3天5時", RowStyle.NORMAL)
    assert column.hover.lines[0] == HoverLineVM("5 小時", "0%", Level.OK, "已重置 · 更新中")
    tray = build_tray_vm([CLAUDE], {"claude": state}, NOW, tz=TPE)
    assert tray.bars[0] == TrayBar(0, Level.OK)
    assert "5h 已重置 · 更新中" in tray.tooltip


def test_reset_exactly_now_counts_as_passed() -> None:
    u = Usage(Window(True, 80, NOW, "5h"), win(18, 4 * D, "7d"), NOW - 2 * M)
    (column,) = vm({"claude": ok("claude", u)}, [CLAUDE]).columns
    assert column.rows[0].text == "已重置 · 更新中"


# ---------------------------------------------------------------- 系統匣圖示畫哪個服務


def _tray_bars(icon: str | None, states: dict[str, ProviderState], providers=BOTH, used_at=None):  # type: ignore[no-untyped-def]
    return build_tray_vm(providers, states, NOW, TPE, icon_provider=icon, used_at=used_at).bars


BOTH_OK = {"claude": ok("claude", CLAUDE_NORMAL), "codex": ok("codex", CODEX_NORMAL)}


def test_tray_icon_chosen_service() -> None:
    assert _tray_bars("codex", BOTH_OK) == (TrayBar(12, Level.OK), TrayBar(6, Level.OK))
    assert _tray_bars("claude", BOTH_OK) == (TrayBar(42, Level.OK), TrayBar(18, Level.OK))


def test_tray_icon_falls_back_to_first_enabled() -> None:
    """選的服務沒啟用（或不認得）：照舊畫第一個啟用的服務。"""
    assert _tray_bars("codex", {"claude": ok("claude", CLAUDE_NORMAL)}, [CLAUDE]) == (
        TrayBar(42, Level.OK),
        TrayBar(18, Level.OK),
    )
    assert _tray_bars("cursor", BOTH_OK)[0] == TrayBar(42, Level.OK)
    assert _tray_bars(None, BOTH_OK)[0] == TrayBar(42, Level.OK)


def test_tray_icon_auto_follows_recent_use() -> None:
    """自動：哪個監控對象的用量剛增加，就畫哪個；重置造成的下降不算。"""
    recent = RecentUse()
    for state in BOTH_OK.values():
        recent.update(state)  # 第一次看到：還不知道有沒有在用
    assert recent.used_at == {}
    codex_up = ok("codex", usage(15, 3 * H, 6, 29 * D, long_label="30d", fetched=NOW))
    recent.update(codex_up)
    states = {"claude": BOTH_OK["claude"], "codex": codex_up}
    assert recent.used_at == {"codex": NOW}
    assert _tray_bars("auto", states, used_at=recent.used_at)[0] == TrayBar(15, Level.OK)

    claude_up = ok("claude", usage(50, 2 * H, 18, 4 * D, fetched=NOW + M))
    recent.update(claude_up)
    states["claude"] = claude_up
    assert _tray_bars("auto", states, used_at=recent.used_at)[0] == TrayBar(50, Level.OK)

    claude_reset = ok("claude", usage(0, 5 * H, 18, 4 * D, fetched=NOW + 2 * M))  # 下降：不算
    recent.update(claude_reset)
    assert recent.used_at["claude"] == NOW + M


def test_recent_use_ignores_errors_stale_and_repeats() -> None:
    recent = RecentUse()
    recent.update(BOTH_OK["claude"])
    recent.update(BOTH_OK["claude"])  # 同一筆資料
    stale = replace(ok("claude", usage(90, 2 * H, 30, 4 * D, fetched=NOW)), stale=True)
    recent.update(stale)
    assert recent.used_at == {}


def test_tray_icon_auto_before_any_use_prefers_5h_and_7d() -> None:
    """剛開程式還不知道：先看同時有 5h 與 7d 的（付費方案），再比用量。"""
    codex_30d_only = Usage(Window(label="5h"), win(95, 20 * D, "30d"), NOW - 2 * M)
    states = {"claude": ok("claude", CLAUDE_NORMAL), "codex": ok("codex", codex_30d_only)}
    assert _tray_bars("auto", states)[0] == TrayBar(42, Level.OK)  # Codex 95% 但只有 30 天
    codex_high = usage(12, 3 * H, 95, 20 * D)
    states["codex"] = ok("codex", codex_high)
    assert _tray_bars("auto", states) == (TrayBar(12, Level.OK), TrayBar(95, Level.CRIT))
    only_30d = {"codex": ok("codex", codex_30d_only)}
    assert _tray_bars("auto", only_30d)[1] == TrayBar(95, Level.CRIT)  # 沒有付費的就比全部


def test_tray_icon_auto_skips_errors_and_passed_resets() -> None:
    claude_err = ProviderState(
        "claude", usage=None, error=PollError(ErrKind.AUTH, "找不到"), stale=False,
        source_label=None,
    )  # fmt: skip
    states = {"claude": claude_err, "codex": ok("codex", CODEX_NORMAL)}
    assert _tray_bars("auto", states, used_at={"claude": NOW})[0] == TrayBar(12, Level.OK)
    reset = usage(100, -1 * H, 5, 3 * D)  # 5h 已重置，實際只剩 7d 5%
    codex = ok("codex", usage(12, 3 * H, 6, 3 * D))
    assert _tray_bars("auto", {"claude": ok("claude", reset), "codex": codex})[0] == TrayBar(
        12, Level.OK
    )


def test_tray_icon_auto_tie_keeps_order_and_nothing_loaded() -> None:
    same = {"claude": ok("claude", CLAUDE_NORMAL), "codex": ok("codex", CLAUDE_NORMAL)}
    assert _tray_bars("auto", same)[0] == TrayBar(42, Level.OK)
    assert _tray_bars("auto", {}) == (None, None)


def test_update_status_shows_percent_and_starting() -> None:
    from usage_monitor.core.i18n import Lang
    from usage_monitor.services.self_update import InstallStatus
    from usage_monitor.services.update_check import UpdateState, UpdateStatus
    from usage_monitor.ui.viewmodel import update_status_text

    s = UpdateState("1.3.0", UpdateStatus.AVAILABLE, "1.4.0")
    assert update_status_text(s, Lang.ZH_TW, InstallStatus.DOWNLOADING) == "正在下載 v1.4.0…"
    assert (
        update_status_text(s, Lang.ZH_TW, InstallStatus.DOWNLOADING, 45) == "正在下載 v1.4.0… 45%"
    )
    assert (
        update_status_text(s, Lang.EN, InstallStatus.DOWNLOADING, 45) == "Downloading v1.4.0… 45%"
    )
    assert update_status_text(s, Lang.ZH_TW, InstallStatus.STARTING) == "正在啟動 v1.4.0…"
    assert update_status_text(s, Lang.EN, InstallStatus.STARTING) == "Starting v1.4.0…"
