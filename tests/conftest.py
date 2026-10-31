from __future__ import annotations

import os
import sys

import pytest

# pytest-qt 測試不開真視窗
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 沒有圖形函式庫的環境（例如 ubuntu CI 沒裝 libEGL）連 import QtGui 都會失敗；
# 這種情況直接不收集 Qt 測試，它們在 windows CI 跑
try:
    import PySide6.QtGui  # noqa: F401
except ImportError:
    collect_ignore_glob = ["ui/test_qt_smoke.py", "ui/test_settings_dialog.py"]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if sys.platform == "win32":
        return
    skip = pytest.mark.skip(reason="需要 Windows")
    for item in items:
        if "windows" in item.keywords:
            item.add_marker(skip)
