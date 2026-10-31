"""浮動小工具視窗：處理滑鼠事件，繪製交給 painter。

視窗屬性：無邊框、置頂、Tool（不出現在工作列與 Alt+Tab）、半透明背景、顯示時不啟用、
WS_EX_NOACTIVATE（點擊不搶焦點）。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QContextMenuEvent, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from usage_monitor.platform import topmost
from usage_monitor.ui import theme
from usage_monitor.ui.theme import Palette
from usage_monitor.ui.viewmodel import ColumnVM, WidgetVM
from usage_monitor.ui.widget import painter, placement

DRAG_START_PX = 3


class UsageWidget(QWidget):
    refresh_requested = Signal()
    menu_requested = Signal(QPoint)
    drag_finished = Signal()
    hover_column = Signal(object, QRect)
    """(ColumnVM | None, 該欄的全域範圍)：滑鼠停留 0.5 秒後送出；離開時送出 None。"""

    def __init__(self, vm: WidgetVM, palette: Palette, opacity: float = 0.9) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setWindowTitle("用量監控")

        self._vm = vm
        self._palette = palette
        self._opacity = opacity
        self._layout = painter.layout(vm)
        self._press: QPoint | None = None
        self._press_window: QPoint | None = None
        self._dragging = False
        self._hover_index: int | None = None
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(theme.HOVER_DELAY_MS)
        self._hover_timer.timeout.connect(self._emit_hover)
        self.setFixedSize(self._layout.width, self._layout.height)

    # ---------------------------------------------------------------- 狀態

    @property
    def vm(self) -> WidgetVM:
        return self._vm

    def set_vm(self, vm: WidgetVM) -> None:
        self._vm = vm
        self._layout = painter.layout(vm)
        old_width = self.width()
        if (old_width, self.height()) != (self._layout.width, self._layout.height):
            self.setFixedSize(self._layout.width, self._layout.height)
            if not self._dragging and self.screen() is not None:
                g = self.screen().availableGeometry()
                work = placement.Rect(g.x(), g.y(), g.width(), g.height())
                x, y = placement.keep_anchor(
                    (self.x(), self.y()), old_width, self._layout.width, work
                )
                self.move(x, y)
        self.update()

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_opacity(self, opacity: float) -> None:
        self._opacity = opacity
        self.update()

    @property
    def hwnd(self) -> int:
        return int(self.winId())

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 的命名
        super().showEvent(event)
        topmost.make_noactivate(self.hwnd)
        topmost.reassert_topmost(self.hwnd)

    # ---------------------------------------------------------------- 繪製

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        painter.paint(p, self._vm, self._palette, opacity=self._opacity, dragging=self._dragging)
        p.end()

    # ---------------------------------------------------------------- 滑鼠

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self._vm.locked:
            self._press = event.globalPosition().toPoint()
            self._press_window = self.pos()
        self._cancel_hover()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._press is not None and self._press_window is not None:
            delta = event.globalPosition().toPoint() - self._press
            if not self._dragging and delta.manhattanLength() >= DRAG_START_PX:
                self._dragging = True
                self.update()
            if self._dragging:
                self.move(self._press_window + delta)
            return
        self._track_hover(event.position().toPoint())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        was_dragging = self._dragging
        self._press = self._press_window = None
        self._dragging = False
        if was_dragging:
            self.update()
            self.drag_finished.emit()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.refresh_requested.emit()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        self._cancel_hover()
        self.menu_requested.emit(event.globalPos())

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._cancel_hover()
        super().leaveEvent(event)

    # ---------------------------------------------------------------- 懸停

    def column_at(self, pos: QPoint) -> int | None:
        for i, rect in enumerate(self._layout.columns):
            if rect.adjusted(-6, 0, 6, 0).contains(pos):
                return i
        return None

    def _track_hover(self, pos: QPoint) -> None:
        index = self.column_at(pos)
        if index == self._hover_index:
            return
        self._cancel_hover()
        self._hover_index = index
        if index is not None:
            self._hover_timer.start()

    def _emit_hover(self) -> None:
        if self._hover_index is None or self._hover_index >= len(self._vm.columns):
            return
        column: ColumnVM = self._vm.columns[self._hover_index]
        rect = self._layout.columns[self._hover_index]
        top_left = self.mapToGlobal(QPoint(rect.x() - 12, 0))
        self.hover_column.emit(column, QRect(top_left, self.size()))

    def _cancel_hover(self) -> None:
        self._hover_timer.stop()
        if self._hover_index is not None:
            self._hover_index = None
            self.hover_column.emit(None, QRect())
