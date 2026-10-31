"""懸停詳細卡（設計稿畫板 3-A）：停留 0.5 秒後在小工具上方出現，顯示確切重置時刻與資料來源。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from usage_monitor.core.i18n import Lang, t
from usage_monitor.ui.theme import Palette
from usage_monitor.ui.viewmodel import HoverVM
from usage_monitor.ui.widget.painter import font

PAD = 14
GAP = 6
LINE_H = 22
LABEL_W = 70
PERCENT_W = 52
MIN_W = 300


class HoverCard(QWidget):
    def __init__(self, palette: Palette) -> None:
        super().__init__(
            None,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._palette = palette
        self._lang = Lang.ZH_TW
        self._vm: HoverVM | None = None

    def set_lang(self, lang: Lang) -> None:
        self._lang = lang

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def show_for(self, vm: HoverVM, anchor: QRect, screen_area: QRect) -> None:
        """在 anchor（小工具上的那一欄，全域座標）上方顯示；上方放不下就放下方。"""
        self._vm = vm
        size = self._measure(vm)
        self.setFixedSize(size[0], size[1])
        x = min(max(anchor.x(), screen_area.left()), screen_area.right() - size[0])
        y = anchor.y() - size[1] - GAP
        if y < screen_area.top():
            y = anchor.bottom() + GAP
        self.move(QPoint(x, y))
        self.show()
        self.update()

    def _measure(self, vm: HoverVM) -> tuple[int, int]:
        body = QFontMetrics(font(13))
        detail_w = max((body.horizontalAdvance(line.detail) for line in vm.lines), default=0)
        width = max(MIN_W, PAD * 2 + LABEL_W + PERCENT_W + detail_w + 8)
        lines = len(vm.lines) + (1 if vm.error else 0) + (0 if vm.lines or vm.error else 1)
        height = PAD + 24 + lines * LINE_H + 12 + 22 + PAD - 4
        return width, height

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt 的命名
        vm, pal = self._vm, self._palette
        if vm is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(pal.border), 1))
        p.setBrush(QColor(pal.bg))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)

        left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        y = PAD
        p.setFont(font(14, bold=True))
        p.setPen(QColor(pal.text))
        p.drawText(QRect(PAD, y, w - PAD * 2, 22), left, vm.title)
        if vm.source:
            p.setFont(font(11))
            p.setPen(QColor(pal.text_secondary))
            p.drawText(QRect(PAD, y, w - PAD * 2, 22), right, vm.source)
        y += 24

        for line in vm.lines:
            p.setFont(font(13))
            p.setPen(QColor(pal.text_secondary))
            p.drawText(QRect(PAD, y, LABEL_W, LINE_H), left, line.label)
            p.setFont(font(13, bold=True))
            color = pal.level_color(line.level) if line.level is not None else pal.text_dim
            p.setPen(QColor(color))
            p.drawText(QRect(PAD + LABEL_W, y, PERCENT_W, LINE_H), left, line.percent)
            p.setFont(font(13))
            p.setPen(QColor(pal.text))
            p.drawText(QRect(PAD + LABEL_W + PERCENT_W, y, w, LINE_H), left, line.detail)
            y += LINE_H
        if vm.error:
            p.setFont(font(12))
            p.setPen(QColor(pal.error_text))
            p.drawText(QRect(PAD, y, w - PAD * 2, LINE_H), left, vm.error)
            y += LINE_H
        if not vm.lines and not vm.error:
            p.setFont(font(12))
            p.setPen(QColor(pal.text_dim))
            p.drawText(QRect(PAD, y, w - PAD * 2, LINE_H), left, t(self._lang, "loading"))
            y += LINE_H

        y += 6
        p.setPen(QPen(QColor(pal.divider), 1))
        p.drawLine(PAD, y, w - PAD, y)
        y += 6
        p.setFont(font(11))
        p.setPen(QColor(pal.text_secondary))
        p.drawText(QRect(PAD, y, w - PAD * 2, 22), left, vm.updated or "")
        p.drawText(QRect(PAD, y, w - PAD * 2, 22), right, vm.hint)
        p.end()
