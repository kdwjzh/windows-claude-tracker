"""系統匣圖示（設計稿畫板 4）：64×64 深色圓角底，上條 5h、下條 7d；右上角紅點／灰點。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from usage_monitor.core.levels import Level
from usage_monitor.ui import theme
from usage_monitor.ui.viewmodel import Dot, TrayBar, TrayVM

S = theme.TRAY_SIZE
BAR_X, BAR_W, BAR_H = 8.0, 48.0, 16.0
BAR_TOP = (14.0, 36.0)
DOT_D = 20.0


APP_ICON_VM = TrayVM(bars=(TrayBar(62, Level.OK), TrayBar(34, Level.OK)), dot=None, tooltip="")
"""讀不到 assets/app.ico 時的備用視窗圖示：與系統匣同樣的兩條用量條。"""
APP_ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_pixmap(vm: TrayVM, size: int = S) -> QPixmap:
    """依 64×64 的座標繪製，再縮放到 size（大尺寸也是向量畫的，不會糊）。"""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / S, size / S)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme.TRAY_BG))
    p.drawRoundedRect(QRectF(0, 0, S, S), 12, 12)

    for top, bar in zip(BAR_TOP, vm.bars, strict=True):
        _bar(p, top, bar)

    if vm.dot is not None:
        color = theme.TRAY_DOT_RED if vm.dot is Dot.RED else theme.TRAY_DOT_GRAY
        p.setBrush(QColor(theme.TRAY_BG))
        p.drawEllipse(QRectF(S - DOT_D - 2, -1, DOT_D + 4, DOT_D + 4))
        p.setBrush(QColor(color))
        p.drawEllipse(QRectF(S - DOT_D, 1, DOT_D, DOT_D))
    if vm.update_dot:
        p.setBrush(QColor(theme.TRAY_BG))
        p.drawEllipse(QRectF(S - DOT_D - 2, S - DOT_D - 3, DOT_D + 4, DOT_D + 4))
        p.setBrush(QColor(theme.TRAY_DOT_BLUE))
        p.drawEllipse(QRectF(S - DOT_D, S - DOT_D - 1, DOT_D, DOT_D))
    p.end()
    return pix


def _bar(p: QPainter, top: float, bar: TrayBar | None) -> None:
    p.setBrush(QColor(theme.TRAY_TRACK))
    p.drawRoundedRect(QRectF(BAR_X, top, BAR_W, BAR_H), 4, 4)
    if bar is None or bar.percent <= 0:
        return
    width = max(BAR_H / 2, BAR_W * min(bar.percent, 100) / 100)
    p.setBrush(QColor(theme.DARK.level_color(bar.level)))
    p.drawRoundedRect(QRectF(BAR_X, top, width, BAR_H), 4, 4)


def render(vm: TrayVM) -> QIcon:
    return QIcon(render_pixmap(vm))


def app_icon(ico: Path | None = None) -> QIcon:
    """設定視窗等一般視窗的圖示：用 assets/app.ico；檔案不存在或讀不到時改用程式繪製的圖示。

    系統匣圖示不用這個，仍依 TrayVM 動態繪製（render）。
    """
    if ico is not None and ico.is_file():
        loaded = QIcon(str(ico))
        if loaded.availableSizes():  # 檔案壞掉或缺 ico 外掛時是空的
            return loaded
    result = QIcon()
    for size in APP_ICON_SIZES:
        result.addPixmap(render_pixmap(APP_ICON_VM, size))
    return result
