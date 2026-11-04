"""儀表板「用量」頁：每個 AI 監控對象一張卡片（目前數字、7 天折線、每期長條、平均）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from usage_monitor.core.i18n import Lang, t
from usage_monitor.ui.settings_dialog.charts import BarChart, LineChart
from usage_monitor.ui.theme import DialogPalette
from usage_monitor.ui.usage_vm import ServiceUsageVM


def _label(text: str, name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


class UsagePanel(QWidget):
    def __init__(self, title: str, palette: DialogPalette, lang: Lang) -> None:
        super().__init__()
        self.setObjectName("card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        empty = t(lang, "usage_no_data")
        self.title = _label(title, "cardTitle")
        self.current = _label("", "valueLabel")
        self.error = _label("", "statusError")
        self.line_title = _label("", "cardSubtitle")
        self.line = LineChart(palette, empty)
        self.bars_title = _label("", "cardSubtitle")
        self.bars = BarChart(palette, empty)
        self.average = _label("", "cardSubtitle")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(6)
        for w in (self.title, self.current, self.error, self.line_title, self.line):
            lay.addWidget(w)
        lay.addSpacing(6)
        for w in (self.bars_title, self.bars, self.average):
            lay.addWidget(w)
        # 放進版面之後才設定顯示（沒有父元件的 QLabel 會被開成獨立視窗，見 SettingCard）
        self.error.setVisible(False)
        self.average.setVisible(False)

    def set_vm(self, vm: ServiceUsageVM) -> None:
        self.current.setText(
            "\n".join(f"{line.label}  {line.percent} · {line.detail}" for line in vm.lines)
        )
        self.current.setVisible(bool(vm.lines))
        self.error.setText(vm.error or "")
        self.error.setVisible(vm.error is not None)
        self.line_title.setText(vm.line_title)
        self.line.set_vm(vm.line)
        self.line_title.setVisible(vm.show_line)
        self.line.setVisible(vm.show_line)
        self.bars_title.setText(vm.bars_title)
        self.bars.set_bars(vm.bars)
        self.average.setText(vm.average or "")
        self.average.setVisible(vm.average is not None)

    def set_palette(self, palette: DialogPalette) -> None:
        self.line.set_palette(palette)
        self.bars.set_palette(palette)
