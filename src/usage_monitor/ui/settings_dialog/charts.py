"""儀表板「用量」頁的兩張小圖：用 QPainter 自己畫（不引入 QtCharts，exe 才不會變大）。

只畫 ui.usage_vm 給的資料，不對資料做任何假設；沒有資料時顯示一行提示。
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from usage_monitor.ui.theme import CHART_HEIGHT, DialogPalette, dialog_levels
from usage_monitor.ui.usage_vm import BarVM, LineVM
from usage_monitor.ui.viewmodel import percent_text

_LEFT = 40
_BOTTOM = 22
_TOP = 18
_RIGHT = 8
_BAR_MAX_W = 36


class _Chart(QWidget):
    def __init__(self, palette: DialogPalette, empty_text: str) -> None:
        super().__init__()
        self._palette = palette
        self._empty_text = empty_text
        self.setMinimumHeight(CHART_HEIGHT)

    def set_palette(self, palette: DialogPalette) -> None:
        self._palette = palette
        self.update()

    def _plot(self) -> QRectF:
        return QRectF(_LEFT, _TOP, self.width() - _LEFT - _RIGHT, self.height() - _TOP - _BOTTOM)

    def _begin(self) -> QPainter:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = p.font()
        font.setPixelSize(11)
        p.setFont(font)
        return p

    def _grid(self, p: QPainter, plot: QRectF) -> None:
        """0%／50%／100% 三條橫線與刻度文字。"""
        for value in (0, 50, 100):
            y = plot.bottom() - plot.height() * value / 100
            p.setPen(QPen(QColor(self._palette.card_border), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(self._palette.text_secondary))
            box = QRectF(0, y - 8, _LEFT - 6, 16)
            align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            p.drawText(box, align, f"{value}%")

    def _empty(self, p: QPainter, plot: QRectF) -> None:
        p.setPen(QColor(self._palette.text_secondary))
        p.drawText(plot, Qt.AlignmentFlag.AlignCenter, self._empty_text)


class LineChart(_Chart):
    """過去 7 天的短週期（5h）用量折線。"""

    def __init__(self, palette: DialogPalette, empty_text: str) -> None:
        super().__init__(palette, empty_text)
        self.vm: LineVM | None = None

    def set_vm(self, vm: LineVM) -> None:
        self.vm = vm
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt 的命名
        p = self._begin()
        plot = self._plot()
        self._grid(p, plot)
        vm = self.vm
        span = (vm.end - vm.start).total_seconds() if vm else 0
        if vm is None or span <= 0:
            p.end()
            return

        def point(at: datetime, percent: float) -> QPointF:
            return QPointF(
                plot.left() + plot.width() * (at - vm.start).total_seconds() / span,
                plot.bottom() - plot.height() * min(max(percent, 0.0), 100.0) / 100,
            )

        p.setPen(QColor(self._palette.text_secondary))
        for at, label in vm.ticks:
            x = plot.left() + plot.width() * (at - vm.start).total_seconds() / span
            box = QRectF(x - 24, plot.bottom() + 4, 48, _BOTTOM - 4)
            if box.left() >= 0 and box.right() <= self.width():
                p.drawText(box, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, label)
        if not vm.segments:
            self._empty(p, plot)
            p.end()
            return
        accent = QColor(self._palette.accent)
        p.setPen(QPen(accent, 2))
        for seg in vm.segments:
            points = [point(at, percent) for at, percent in seg]
            if len(points) == 1:
                p.setBrush(accent)
                p.drawEllipse(points[0], 2.5, 2.5)
                p.setBrush(Qt.BrushStyle.NoBrush)
            else:
                p.drawPolyline(points)
        p.end()


class BarChart(_Chart):
    """長週期每一期的最高用量（綠／黃／紅與小工具相同）。"""

    def __init__(self, palette: DialogPalette, empty_text: str) -> None:
        super().__init__(palette, empty_text)
        self.bars: tuple[BarVM, ...] = ()

    def set_bars(self, bars: tuple[BarVM, ...]) -> None:
        self.bars = bars
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt 的命名
        p = self._begin()
        plot = self._plot()
        self._grid(p, plot)
        if not self.bars:
            self._empty(p, plot)
            p.end()
            return
        levels = dialog_levels(self._palette)
        slot = plot.width() / len(self.bars)
        width = min(_BAR_MAX_W, slot * 0.6)
        for i, bar in enumerate(self.bars):
            center = plot.left() + slot * (i + 0.5)
            height = plot.height() * min(max(bar.percent, 0.0), 100.0) / 100
            rect = QRectF(center - width / 2, plot.bottom() - height, width, height)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(levels.level_color(bar.level)))
            p.drawRoundedRect(rect, 2, 2)
            p.setPen(QColor(self._palette.text))
            above = QRectF(center - slot / 2, rect.top() - 16, slot, 14)
            p.drawText(above, Qt.AlignmentFlag.AlignCenter, percent_text(bar.percent))
            p.setPen(QColor(self._palette.text_secondary))
            below = QRectF(center - slot / 2, plot.bottom() + 4, slot, _BOTTOM - 4)
            p.drawText(below, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, bar.label)
        p.end()
