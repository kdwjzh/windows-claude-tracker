"""結束程式不能被「關閉只是隱藏」的視窗擋下來。

2026-11-05 bug：儀表板開著時按「立即更新」，新版已啟動，舊版卻沒結束。
app.quit() 會先請所有視窗關閉，儀表板與診斷視窗的 closeEvent 會 ignore（只隱藏），
Qt 依視窗順序（不固定）可能因此取消結束，所以時好時壞；選單的「結束」也一樣。
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytestqt")

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QWidget

from usage_monitor import bootstrap

pytestmark = pytest.mark.qt


class HideOnClose(QWidget):
    """跟儀表板一樣：關閉只是隱藏。"""

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt 的命名
        event.ignore()
        self.hide()


def test_quit_is_not_cancelled_by_hide_on_close_window(qapp: QApplication) -> None:
    windows = [HideOnClose(), *(QWidget() for _ in range(20))]  # 多開幾個，順序不固定也幾乎必中
    for w in windows:
        w.show()
    guard = QTimer()  # 結束被取消時的保險；測完要停掉，否則會打斷後面測試的事件迴圈
    guard.setSingleShot(True)
    guard.timeout.connect(lambda: qapp.exit(1))
    try:
        QTimer.singleShot(0, lambda: bootstrap.quit_app(qapp))
        guard.start(2000)
        assert qapp.exec() == 0
    finally:
        guard.stop()
        for w in windows:
            w.hide()
            w.deleteLater()
