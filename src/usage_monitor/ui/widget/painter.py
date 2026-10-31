"""依 WidgetVM 繪製小工具（設計稿第一版畫板 1、2）。只畫，不處理事件。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen

from usage_monitor.ui import theme
from usage_monitor.ui.theme import METRICS, Metrics, Palette
from usage_monitor.ui.viewmodel import ColumnVM, NoteKind, RowStyle, RowVM, WidgetVM


def font(px: int, *, bold: bool = False) -> QFont:
    f = QFont()
    f.setFamilies(theme.FONT_FAMILIES)
    f.setPixelSize(px)
    f.setBold(bold)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


ERROR_MARK = "!"
ERROR_MARK_GAP = 8


@cache
def _metrics(px: int, bold: bool = False) -> QFontMetrics:
    return QFontMetrics(font(px, bold=bold))


def row_text_width(row: RowVM, m: Metrics = METRICS) -> int:
    """這一列文字（含錯誤時的「!」）實際畫出來的寬度。"""
    width = _metrics(m.row_px).horizontalAdvance(row.text)
    if row.style is RowStyle.ERROR:
        width += _metrics(m.row_px, bold=True).horizontalAdvance(ERROR_MARK) + ERROR_MARK_GAP
    return width


def title_width(c: ColumnVM, m: Metrics = METRICS) -> int:
    text = f"{c.title} · {c.note}" if c.note else c.title
    return _metrics(m.title_px).horizontalAdvance(text)


def label_width(c: ColumnVM, m: Metrics = METRICS) -> int:
    """週期標籤區：至少 label_w；「30d」較寬時依實際寬度＋label_gap，不會貼到進度條。"""
    widest = max((_metrics(m.row_px).horizontalAdvance(r.label) for r in c.rows), default=0)
    return max(m.label_w, widest + m.label_gap)


def column_width(c: ColumnVM, m: Metrics = METRICS) -> int:
    """欄寬跟著這一欄目前的文字：最長一列的寬度＋text_slack，標題放不下時以標題為準。"""
    text_w = max((row_text_width(r, m) for r in c.rows), default=0)
    rows_w = label_width(c, m) + m.bar_w + m.bar_text_gap + text_w + m.text_slack
    return max(rows_w, title_width(c, m) + m.text_slack)


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    columns: tuple[QRect, ...]
    """每一欄的範圍（懸停卡判斷滑鼠在哪一欄）。"""


def layout(vm: WidgetVM, m: Metrics = METRICS) -> Layout:
    left = m.handle_pad_l + m.handle_w + m.handle_pad_r
    rows = max((len(c.rows) for c in vm.columns), default=2)
    height = m.pad_t + m.title_h + rows * m.row_h + m.pad_b
    rects: list[QRect] = []
    x = left
    for i, column in enumerate(vm.columns):
        if i:
            x += m.col_gap
        col_w = column_width(column, m)
        rects.append(QRect(x, 0, col_w, height))
        x += col_w
    if not vm.columns:
        x += m.label_w + m.bar_w
    return Layout(width=x + m.pad_r, height=height, columns=tuple(rects))


def _color(value: str, alpha: float = 1.0) -> QColor:
    c = QColor(value)
    c.setAlphaF(alpha)
    return c


def paint(
    p: QPainter,
    vm: WidgetVM,
    palette: Palette,
    *,
    opacity: float = 1.0,
    dragging: bool = False,
    m: Metrics = METRICS,
) -> None:
    lay = layout(vm, m)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    # 面板：只有背景套用不透明度，文字與進度條維持清楚
    panel = QRectF(0.5, 0.5, lay.width - 1, lay.height - 1)
    border = _color(palette.drag_border) if dragging else _color(palette.border)
    p.setPen(QPen(border, 1.5 if dragging else m.border))
    p.setBrush(_color(palette.bg, opacity))
    p.drawRoundedRect(panel, m.radius, m.radius)

    _paint_handle(p, vm.locked, palette, lay.height, m)
    for i, (column, rect) in enumerate(zip(vm.columns, lay.columns, strict=True)):
        if i:
            x = rect.x() - m.col_gap / 2
            p.setPen(QPen(_color(palette.divider), 1))
            p.drawLine(QPointF(x, m.pad_t + 2), QPointF(x, lay.height - m.pad_b - 2))
        _paint_column(p, column, rect, palette, m)


def _paint_handle(p: QPainter, locked: bool, palette: Palette, height: int, m: Metrics) -> None:
    x = m.handle_pad_l
    if not locked:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_color(palette.handle))
        p.drawRoundedRect(
            QRectF(x, m.pad_t + 2, m.handle_w, height - m.pad_t - m.pad_b - 4), 1.5, 1.5
        )
        return
    # 鎖頭：U 形鎖環＋方形鎖身
    cx, cy = x + m.handle_w / 2, height / 2 + 3
    pen = QPen(_color(palette.text_secondary), 1.4)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    shackle = QPainterPath()
    shackle.moveTo(cx - 3, cy - 2)
    shackle.lineTo(cx - 3, cy - 5)
    shackle.arcTo(QRectF(cx - 3, cy - 8, 6, 6), 180, -180)
    shackle.lineTo(cx + 3, cy - 2)
    p.drawPath(shackle)
    p.drawRoundedRect(QRectF(cx - 4.5, cy - 2, 9, 7), 1.5, 1.5)


def _paint_column(p: QPainter, c: ColumnVM, rect: QRect, palette: Palette, m: Metrics) -> None:
    title_font = font(m.title_px)
    p.setFont(title_font)
    p.setPen(_color(palette.text_secondary))
    title_rect = QRect(rect.x(), m.pad_t, rect.width(), m.title_h)
    p.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, c.title)
    if c.note:
        offset = QFontMetrics(title_font).horizontalAdvance(c.title)
        color = palette.error_text if c.note_kind is NoteKind.ERROR else palette.text_dim
        p.setPen(_color(color))
        note_rect = title_rect.adjusted(offset, 0, 0, 0)
        p.drawText(
            note_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f" · {c.note}"
        )

    y = m.pad_t + m.title_h
    label_w = label_width(c, m)
    for row in c.rows:
        _paint_row(p, row, rect, label_w, y, palette, m)
        y += m.row_h


def _paint_row(
    p: QPainter, row: RowVM, rect: QRect, label_w: int, y: int, palette: Palette, m: Metrics
) -> None:
    x = rect.x()
    row_font = font(m.row_px)
    p.setFont(row_font)
    center = y + m.row_h / 2

    p.setPen(_color(palette.text_secondary))
    p.drawText(
        QRectF(x, y, label_w, m.row_h),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        row.label,
    )

    # 10 格分段進度條
    bx = x + label_w
    top = center - m.seg_h / 2
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(m.segments):
        if row.style is RowStyle.ERROR:
            color = palette.seg_error
        elif i < row.filled and row.level is not None:
            color = palette.level_color(row.level, stale=row.style is RowStyle.STALE)
        else:
            color = palette.seg_empty
        p.setBrush(_color(color))
        p.drawRoundedRect(
            QRectF(bx + i * (m.seg_w + m.seg_gap), top, m.seg_w, m.seg_h),
            m.seg_radius,
            m.seg_radius,
        )

    tx = bx + m.bar_w + m.bar_text_gap
    text_rect = QRectF(tx, y, rect.right() + 1 - tx, m.row_h)
    align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    if row.style is RowStyle.ERROR:
        bold = font(m.row_px, bold=True)
        p.setFont(bold)
        p.setPen(_color(palette.error_mark))
        p.drawText(text_rect, align, ERROR_MARK)
        p.setFont(row_font)
        p.setPen(_color(palette.text_dim))
        p.drawText(
            text_rect.adjusted(
                _metrics(m.row_px, bold=True).horizontalAdvance(ERROR_MARK) + ERROR_MARK_GAP,
                0, 0, 0,
            ),
            align,
            row.text,
        )  # fmt: skip
        return
    color = palette.text_dim if row.style in (RowStyle.STALE, RowStyle.EMPTY) else palette.text
    p.setPen(_color(color))
    p.drawText(text_rect, align, row.text)
