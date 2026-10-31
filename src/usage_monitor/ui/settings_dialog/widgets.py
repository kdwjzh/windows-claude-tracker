"""設定視窗用的小元件：Windows 11 風格的開關、設定卡片、區段標題、快捷鍵擷取。"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from usage_monitor.core.i18n import Lang, t
from usage_monitor.ui.theme import DialogPalette


class ToggleSwitch(QAbstractButton):
    """圓角開關：開＝填滿強調色、圓點在右；關＝外框、圓點在左。"""

    def __init__(self, palette: DialogPalette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._palette = palette

    def set_palette(self, palette: DialogPalette) -> None:
        self._palette = palette
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt 的命名
        return QSize(40, 20)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        pal = self._palette
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        radius = r.height() / 2
        if self.isChecked():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(pal.accent))
            p.drawRoundedRect(r, radius, radius)
            p.setBrush(QColor(pal.accent_text))
            d = r.height() - 8
            p.drawEllipse(QRectF(r.right() - d - 4, r.top() + 4, d, d))
        else:
            p.setPen(QColor(pal.switch_off_border))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, radius, radius)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(pal.switch_off_border))
            d = r.height() - 10
            p.drawEllipse(QRectF(r.left() + 5, r.top() + 5, d, d))
        p.end()


class LabeledSwitch(QWidget):
    """「開啟／關閉」文字＋開關（設計稿把狀態文字放在開關左邊）。"""

    toggled = Signal(bool)

    def __init__(
        self, palette: DialogPalette, lang: Lang = Lang.ZH_TW, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._lang = lang
        self.label = QLabel()
        self.label.setObjectName("switchLabel")
        self.switch = ToggleSwitch(palette)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(self.label)
        lay.addWidget(self.switch)
        self.switch.toggled.connect(self._on_toggled)
        self._sync_label()

    def _on_toggled(self, checked: bool) -> None:
        self._sync_label()
        self.toggled.emit(checked)

    def _sync_label(self) -> None:
        self.label.setText(t(self._lang, "switch_on" if self.switch.isChecked() else "switch_off"))

    def isChecked(self) -> bool:  # noqa: N802 - 與 Qt 一致
        return self.switch.isChecked()

    def set_checked_silently(self, checked: bool) -> None:
        """外部同步狀態用：不送出 toggled，避免又寫一次設定。"""
        self.switch.blockSignals(True)
        self.switch.setChecked(checked)
        self.switch.blockSignals(False)
        self._sync_label()

    def set_palette(self, palette: DialogPalette) -> None:
        self.switch.set_palette(palette)


class SettingCard(QWidget):
    """一張設定卡：左邊標題＋說明，右邊控制項。"""

    def __init__(
        self, title: str, control: QWidget | None = None, subtitle: str | None = None
    ) -> None:
        super().__init__()
        self.setObjectName("card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(16)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("cardTitle")
        texts.addWidget(self.title)
        self.subtitle = QLabel(subtitle or "")
        self.subtitle.setObjectName("cardSubtitle")
        self.subtitle.setVisible(bool(subtitle))
        self.subtitle.setWordWrap(True)
        texts.addWidget(self.subtitle)
        lay.addLayout(texts, 1)
        if control is not None:
            lay.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        self.setMinimumHeight(64)

    def set_subtitle(self, text: str, object_name: str = "cardSubtitle") -> None:
        self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))
        if self.subtitle.objectName() != object_name:
            self.subtitle.setObjectName(object_name)
            self.subtitle.style().unpolish(self.subtitle)
            self.subtitle.style().polish(self.subtitle)


def section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("section")
    return label


class HotkeyButton(QPushButton):
    """按「變更」後擷取下一個組合鍵；Esc 取消。送出 "Ctrl+Alt+U" 格式的字串。"""

    captured = Signal(str)

    def __init__(self, lang: Lang = Lang.ZH_TW) -> None:
        super().__init__(t(lang, "hotkey_change"))
        self._lang = lang
        self._capturing = False
        self.clicked.connect(self._start)

    @property
    def capturing(self) -> bool:
        return self._capturing

    def _start(self) -> None:
        self._capturing = True
        self.setText(t(self._lang, "hotkey_capturing"))
        self.setFocus()
        self.grabKeyboard()

    def _stop(self) -> None:
        self._capturing = False
        self.releaseKeyboard()
        self.setText(t(self._lang, "hotkey_change"))

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if not self._capturing:
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Escape:
            self._stop()
            return
        text = hotkey_text(event.key(), event.modifiers())
        if text is not None:
            self._stop()
            self.captured.emit(text)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        if self._capturing:
            self._stop()
        super().focusOutEvent(event)


_MODIFIER_NAMES = (
    (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
    (Qt.KeyboardModifier.AltModifier, "Alt"),
    (Qt.KeyboardModifier.ShiftModifier, "Shift"),
    (Qt.KeyboardModifier.MetaModifier, "Win"),
)


def hotkey_text(key: int, modifiers: Qt.KeyboardModifier) -> str | None:
    """Qt 的按鍵＋修飾鍵 → "Ctrl+Alt+U"；只按修飾鍵、沒有修飾鍵或不支援的鍵回傳 None。

    支援 A–Z、0–9、F1–F24（與 platform.hotkey.parse 一致）。
    """
    mods = [name for flag, name in _MODIFIER_NAMES if modifiers & flag]
    if not mods:
        return None
    k = int(key)
    if (
        Qt.Key.Key_A.value <= k <= Qt.Key.Key_Z.value
        or Qt.Key.Key_0.value <= k <= Qt.Key.Key_9.value
    ):
        name = chr(k)
    elif Qt.Key.Key_F1.value <= k <= Qt.Key.Key_F24.value:
        name = f"F{k - Qt.Key.Key_F1.value + 1}"
    else:
        return None
    return "+".join([*mods, name])
