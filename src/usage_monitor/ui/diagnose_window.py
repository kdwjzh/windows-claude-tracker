"""診斷結果視窗：在主程式裡跑診斷（不再另外啟動 diagnose.exe），顯示完整輸出。

檢查邏輯在 usage_monitor.diagnose；ui 不能 import 它（同一層、彼此獨立），
所以由 bootstrap 注入「執行診斷並回傳文字」的函式。診斷會讀檔、解密、呼叫 API，
在背景執行緒跑，結果用 Signal 送回主執行緒（CLAUDE.md §5.2 第 5、13 條）。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from usage_monitor.core.i18n import Lang, t
from usage_monitor.ui.settings_dialog.style import stylesheet
from usage_monitor.ui.theme import DialogPalette

log = logging.getLogger(__name__)

RunDiagnostics = Callable[[Lang], str]
"""跑完整診斷，回傳要顯示的文字（輸出語言由參數決定）。"""

_MONO = '"Cascadia Mono", Consolas, "Microsoft JhengHei", monospace'


class DiagnoseWindow(QWidget):
    finished = Signal(str)
    """背景執行緒跑完時 emit；Qt 會自動改用 queued connection 送回主執行緒。"""

    def __init__(self, run: RunDiagnostics, lang: Lang, palette: DialogPalette) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("settingsRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._run = run
        self._lang = lang
        self._palette = palette
        self.running = False
        self.resize(760, 560)

        self.hint = QLabel()
        self.hint.setObjectName("cardSubtitle")
        self.hint.setWordWrap(True)
        self.status = QLabel()
        self.status.setObjectName("valueLabel")
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.copy = QPushButton()
        self.copy.clicked.connect(self._copy)
        self.rerun = QPushButton()
        self.rerun.clicked.connect(self.start)

        buttons = QHBoxLayout()
        buttons.addWidget(self.status, 1)
        buttons.addWidget(self.copy)
        buttons.addWidget(self.rerun)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.addWidget(self.hint)
        lay.addWidget(self.output, 1)
        lay.addLayout(buttons)

        self.finished.connect(self._show_result)
        self.set_lang(lang)
        self.apply_palette(palette)

    def set_lang(self, lang: Lang) -> None:
        """切換語言：換掉介面文字；下一次執行起輸出也用新的語言。"""
        self._lang = lang
        self.setWindowTitle(t(lang, "diag_window_title"))
        self.hint.setText(t(lang, "diag_window_hint"))
        self.copy.setText(t(lang, "diag_copy"))
        self.rerun.setText(t(lang, "diag_rerun"))
        if self.running:
            self.status.setText(t(lang, "diag_running"))
        self.setStyleSheet(self._style())

    def apply_palette(self, palette: DialogPalette) -> None:
        self._palette = palette
        self.setStyleSheet(self._style())

    def _style(self) -> str:
        p = self._palette
        return (
            stylesheet(p, self._lang)
            + f"""
        QPlainTextEdit {{
            background: {p.card}; border: 1px solid {p.card_border}; border-radius: 6px;
            padding: 8px; font-family: {_MONO}; font-size: 13px; font-weight: 400;
        }}
        """
        )

    def show_and_run(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.start()

    def start(self) -> None:
        """在背景執行緒跑診斷；跑的時候按鈕停用、顯示「診斷中…」。"""
        if self.running:
            return
        self.running = True
        self.status.setText(t(self._lang, "diag_running"))
        self.copy.setEnabled(False)
        self.rerun.setEnabled(False)
        self.output.clear()
        threading.Thread(
            target=self._work, args=(self._lang,), name="diagnose", daemon=True
        ).start()

    def _work(self, lang: Lang) -> None:
        try:
            text = self._run(lang)
        except Exception as e:  # 診斷出錯也不能讓程式當掉，只記 log
            log.exception("診斷執行失敗")
            text = t(lang, "diag_window_failed", error=type(e).__name__)
        self.finished.emit(text)

    def _show_result(self, text: str) -> None:
        self.running = False
        self.output.setPlainText(text)
        self.status.setText("")
        self.copy.setText(t(self._lang, "diag_copy"))
        self.copy.setEnabled(True)
        self.rerun.setEnabled(True)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.output.toPlainText())
        self.copy.setText(t(self._lang, "diag_copied"))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt 的命名
        """關閉只是隱藏：背景執行緒跑完時視窗物件還在，結果留到下次開啟。"""
        event.ignore()
        self.hide()
