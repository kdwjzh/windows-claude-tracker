"""pytest-qt 冒煙測試：視窗能建立、能依 VM 重畫、不丟例外（QT_QPA_PLATFORM=offscreen）。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("pytestqt")

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QImage

from fakes import FakeClock
from usage_monitor.core.errors import ErrKind, PollError
from usage_monitor.core.models import ProviderState, Usage, Window
from usage_monitor.services.settings.store import SettingsStore
from usage_monitor.services.state_store import StateStore
from usage_monitor.ui import theme
from usage_monitor.ui.controller import Controller, resolve_palette
from usage_monitor.ui.hovercard import HoverCard
from usage_monitor.ui.tray import icon
from usage_monitor.ui.viewmodel import (
    Dot,
    TrayBar,
    TrayVM,
    build_widget_vm,
)
from usage_monitor.ui.widget import painter
from usage_monitor.ui.widget.widget import UsageWidget

pytestmark = pytest.mark.qt

NOW = datetime(2026, 10, 29, 10, tzinfo=UTC)
PROVIDERS = [("claude", "Claude"), ("codex", "Codex")]


def states() -> dict[str, ProviderState]:
    u = Usage(
        Window(True, 42, NOW + timedelta(hours=2), "5h"),
        Window(True, 93, NOW + timedelta(days=1), "7d"),
        NOW,
    )
    return {
        "claude": ProviderState("claude", u, None, False, "桌面版"),
        "codex": ProviderState("codex", None, PollError(ErrKind.AUTH, "找不到"), False, None),
    }


@pytest.mark.usefixtures("qapp")
@pytest.mark.parametrize(
    "window",
    [
        Window(True, 99.4, NOW + timedelta(hours=23, minutes=59, seconds=30), "5h"),
        Window(True, 99, NOW + timedelta(days=9, hours=23, minutes=30), "7d"),
        Window(True, 99, NOW + timedelta(days=29, hours=1), "30d"),
        Window(True, 100, NOW + timedelta(hours=3), "5h"),
        Window(True, 100, None, "5h"),
        Window(True, 99, NOW, "5h"),
    ],
)
def test_text_has_exactly_slack_after_longest_row(window: Window) -> None:
    """2026-10-29 回報：文字右邊不要留一大塊空白，貼近但不貼齊。

    欄寬跟著這一欄目前的文字：最長一列後面剛好留 text_slack，其他列一定放得下。
    （實際像素依字型而定，所以驗證的是關係，不是絕對寬度。）
    """
    m = theme.METRICS
    short = Window(True, 3, None, "7d")  # 「3%」
    vm = build_widget_vm(
        PROVIDERS[:1],
        {"claude": ProviderState("claude", Usage(window, short, NOW), None, False, None)},
        NOW,
    )
    (column,) = vm.columns
    (rect,) = painter.layout(vm).columns
    text_x = rect.x() + painter.label_width(column) + m.bar_w + m.bar_text_gap
    room = rect.right() + 1 - text_x
    widths = [painter.row_text_width(r) for r in column.rows]
    assert all(w <= room for w in widths), f"{[r.text for r in column.rows]} 放不下"
    title_decides = rect.width() == painter.title_width(column) + m.text_slack
    assert title_decides or room - max(widths) == m.text_slack


@pytest.mark.usefixtures("qapp")
@pytest.mark.parametrize("label", ["5h", "7d", "30d", "365d"])
def test_period_label_never_touches_bar(label: str) -> None:
    """2026-10-29：label_w 縮成 24 時「30d」貼到進度條；標籤區要依實際寬度撐開。"""
    from PySide6.QtGui import QFontMetrics

    m = theme.METRICS
    u = Usage(Window(True, 5, None, "5h"), Window(True, 5, None, label), NOW)
    vm = build_widget_vm(
        PROVIDERS[:1], {"claude": ProviderState("claude", u, None, False, None)}, NOW
    )
    advance = QFontMetrics(painter.font(m.row_px)).horizontalAdvance(label)
    assert painter.label_width(vm.columns[0]) >= advance + m.label_gap


@pytest.mark.usefixtures("qapp")
def test_column_width_follows_its_text() -> None:
    def column_rect(percent: float, resets_in: timedelta | None):
        u = Usage(
            Window(True, percent, NOW + resets_in if resets_in else None, "5h"),
            Window(True, 1, None, "7d"),
            NOW,
        )
        state = {"claude": ProviderState("claude", u, None, False, None)}
        return painter.layout(build_widget_vm(PROVIDERS[:1], state, NOW)).columns[0]

    assert column_rect(0, None).width() < column_rect(99, timedelta(hours=23, minutes=59)).width()


@pytest.mark.usefixtures("qapp")
def test_error_mark_and_title_fit() -> None:
    m = theme.METRICS
    vm = build_widget_vm(PROVIDERS, states(), NOW)
    lay = painter.layout(vm)
    codex = vm.columns[1]  # 未登入：「!」＋「—」，標題「Codex · 未登入」
    rect = lay.columns[1]
    assert painter.row_text_width(codex.rows[0]) > painter.row_text_width(
        replace(codex.rows[0], style=vm.columns[0].rows[0].style)
    )
    assert painter.title_width(codex) + m.text_slack <= rect.width()
    assert lay.width == rect.right() + 1 + m.pad_r


def test_layout_width_depends_on_columns() -> None:
    one = painter.layout(build_widget_vm(PROVIDERS[:1], states(), NOW))
    two = painter.layout(build_widget_vm(PROVIDERS, states(), NOW))
    assert two.width > one.width
    assert len(two.columns) == 2
    assert one.height == two.height


@pytest.mark.parametrize("palette", [theme.DARK, theme.LIGHT])
@pytest.mark.parametrize("locked", [False, True])
def test_widget_paints_all_states(qtbot, palette: theme.Palette, locked: bool) -> None:
    vm = build_widget_vm(PROVIDERS, states(), NOW, locked=locked)
    widget = UsageWidget(vm, palette)
    qtbot.addWidget(widget)
    image = widget.grab().toImage()
    assert not image.isNull()
    assert (image.width(), image.height()) == (widget.width(), widget.height())


def test_widget_resizes_when_columns_change(qtbot) -> None:
    widget = UsageWidget(build_widget_vm(PROVIDERS, states(), NOW), theme.DARK)
    qtbot.addWidget(widget)
    wide = widget.width()
    widget.set_vm(build_widget_vm(PROVIDERS[:1], states(), NOW))
    assert widget.width() < wide


def test_widget_double_click_requests_refresh(qtbot) -> None:
    widget = UsageWidget(build_widget_vm(PROVIDERS, states(), NOW), theme.DARK)
    qtbot.addWidget(widget)
    with qtbot.waitSignal(widget.refresh_requested, timeout=1000):
        qtbot.mouseDClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(50, 20))


def test_widget_drag_moves_and_signals(qtbot) -> None:
    widget = UsageWidget(build_widget_vm(PROVIDERS, states(), NOW), theme.DARK)
    qtbot.addWidget(widget)
    widget.move(100, 100)
    widget.show()
    qtbot.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    qtbot.mouseMove(widget, QPoint(60, 50))
    with qtbot.waitSignal(widget.drag_finished, timeout=1000):
        qtbot.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(60, 50))
    assert widget.pos() != QPoint(100, 100)


def test_column_hit_testing(qtbot) -> None:
    widget = UsageWidget(build_widget_vm(PROVIDERS, states(), NOW), theme.DARK)
    qtbot.addWidget(widget)
    lay = painter.layout(widget.vm)
    assert widget.column_at(lay.columns[1].center()) == 1
    assert widget.column_at(QPoint(2, 2)) is None


def test_hover_card_paints(qtbot) -> None:
    vm = build_widget_vm(PROVIDERS, states(), NOW)
    card = HoverCard(theme.DARK)
    qtbot.addWidget(card)
    for column in vm.columns:
        card.show_for(column.hover, QRect(100, 500, 300, 60), QRect(0, 0, 1920, 1040))
        assert card.y() < 500
        assert not card.grab().toImage().isNull()
    card.show_for(vm.columns[0].hover, QRect(100, 0, 300, 60), QRect(0, 0, 1920, 1040))
    assert card.y() > 0  # 上方放不下 → 放下方


@pytest.mark.parametrize(
    "vm",
    [
        TrayVM((TrayBar(42, theme.Level.OK), TrayBar(93, theme.Level.CRIT)), None, "x"),
        TrayVM((None, None), Dot.RED, "x"),
        TrayVM((TrayBar(0, theme.Level.OK), None), Dot.GRAY, "x"),
    ],
)
def test_tray_icon_renders(qtbot, vm: TrayVM) -> None:
    pix = icon.render_pixmap(vm)
    assert (pix.width(), pix.height()) == (64, 64)
    img: QImage = pix.toImage()
    assert img.pixelColor(32, 32).alpha() == 255  # 底色不透明


def test_app_icon_uses_ico_file(qtbot) -> None:
    from usage_monitor.platform import paths

    sizes = {s.width() for s in icon.app_icon(paths.app_icon_file()).availableSizes()}
    assert {16, 32, 256} <= sizes


@pytest.mark.parametrize("name", ["missing.ico", "broken.ico"])
def test_app_icon_falls_back_to_drawn(qtbot, tmp_path: Path, name: str) -> None:
    if name == "broken.ico":
        (tmp_path / name).write_bytes(b"not an icon")
    sizes = {s.width() for s in icon.app_icon(tmp_path / name).availableSizes()}
    assert sizes == set(icon.APP_ICON_SIZES)


def test_resolve_palette() -> None:
    assert resolve_palette("light", Qt.ColorScheme.Dark) is theme.LIGHT
    assert resolve_palette("dark", Qt.ColorScheme.Light) is theme.DARK
    assert resolve_palette("system", Qt.ColorScheme.Light) is theme.LIGHT
    assert resolve_palette("system", Qt.ColorScheme.Unknown) is theme.DARK


def test_topmost_not_reasserted_while_menu_is_open(
    qtbot, qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-10-30 bug：右鍵選單打開幾秒後被小工具蓋住。

    每 2 秒重設 TOPMOST 會把小工具抬到選單上面；選單開著時要跳過。
    """
    from usage_monitor.ui import controller as controller_module

    calls: list[int] = []
    monkeypatch.setattr(controller_module.topmost, "reassert_topmost", calls.append)
    monkeypatch.setattr(controller_module.fullscreen, "is_foreground_fullscreen", lambda: False)
    store = SettingsStore(tmp_path / "settings.json")
    store.load()
    controller = Controller(
        qapp, store, StateStore(), PROVIDERS, FakeClock(NOW),
        refresh=lambda: None, log_file=tmp_path / "m.log", on_quit=lambda: None,
    )  # fmt: skip
    controller.start()
    try:
        calls.clear()
        controller._on_housekeeping()  # pyright: ignore[reportPrivateUsage]
        assert len(calls) == 1

        controller.widget_menu.popup(QPoint(10, 10))
        qtbot.waitUntil(controller.widget_menu.isVisible, timeout=2000)
        controller._on_housekeeping()  # pyright: ignore[reportPrivateUsage]
        assert len(calls) == 1  # 選單開著：不重設，選單才不會被蓋住

        controller.widget_menu.hide()
        qtbot.waitUntil(lambda: not controller.widget_menu.isVisible(), timeout=2000)
        controller._on_housekeeping()  # pyright: ignore[reportPrivateUsage]
        assert len(calls) == 2  # 選單關掉後恢復
    finally:
        controller.shutdown()


def test_controller_end_to_end(qtbot, qapp, tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    store.load()
    # 斷言用的是中文：明確指定語言，不依賴這台機器的 Windows 語言（CI runner 是英文）
    store.update(lambda s: replace(s, providers=("claude", "codex"), language="zh-TW"))
    state_store = StateStore()
    refreshed: list[int] = []
    quit_called: list[int] = []
    controller = Controller(
        qapp,
        store,
        state_store,
        PROVIDERS,
        FakeClock(NOW),
        refresh=lambda: refreshed.append(1),
        log_file=tmp_path / "monitor.log",
        on_quit=lambda: quit_called.append(1),
    )
    qtbot.addWidget(controller.widget)
    controller.start()
    try:
        assert controller.widget.isVisible()

        # 背景執行緒更新 → Signal → 主執行緒重畫
        for s in states().values():
            state_store.update(s)
        qtbot.waitUntil(lambda: controller.widget.vm.columns[0].rows[0].text.startswith("42%"))
        assert controller.widget.vm.columns[1].note == "未登入"

        controller.set_locked(True)
        assert controller.locked and controller.widget.vm.locked
        controller.set_opacity(0.6)
        assert store.current.widget.opacity == 0.6

        controller.toggle_widget()
        assert not controller.widget.isVisible()
        assert store.current.widget.visible is False
        controller.toggle_widget()
        assert controller.widget.isVisible()

        controller.set_locked(False)
        controller.widget.move(controller.widget.x() - 3, controller.widget.y())
        controller._on_drag_finished()  # pyright: ignore[reportPrivateUsage]
        assert store.current.widget.screen is not None
        controller.reset_position()
        assert store.current.widget.pos is None

        store.update(lambda s: replace(s, widget=replace(s.widget, theme="light")))
        controller.refresh()
        controller.quit()
        assert refreshed == [1] and quit_called == [1]
    finally:
        controller.shutdown()
