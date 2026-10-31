"""系統匣：圖示、提示文字、左鍵切換小工具、右鍵選單、Windows 通知。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from usage_monitor.ui.tray import icon
from usage_monitor.ui.viewmodel import TrayVM, truncate


class Tray(QObject):
    toggle_requested = Signal()
    notification_clicked = Signal()

    def __init__(self, vm: TrayVM, menu: QMenu) -> None:
        super().__init__()
        self._menu = menu
        self._tray = QSystemTrayIcon(icon.render(vm))
        self._tray.setContextMenu(menu)
        self._tray.setToolTip(truncate(vm.tooltip))
        self._tray.activated.connect(self._on_activated)
        self._tray.messageClicked.connect(self.notification_clicked.emit)
        self._vm = vm

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def set_vm(self, vm: TrayVM) -> None:
        if vm == self._vm:
            return
        if (vm.bars, vm.dot, vm.update_dot) != (self._vm.bars, self._vm.dot, self._vm.update_dot):
            self._tray.setIcon(icon.render(vm))
        self._tray.setToolTip(truncate(vm.tooltip))
        self._vm = vm

    def set_menu(self, menu: QMenu) -> None:
        """切換語言時換成重建的選單。"""
        self._menu = menu
        self._tray.setContextMenu(menu)

    def notify(self, title: str, body: str) -> None:
        """只在需要處理時呼叫；body 已含「點這則通知可執行診斷」那一句（依語言）。"""
        self._tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Warning)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_requested.emit()
