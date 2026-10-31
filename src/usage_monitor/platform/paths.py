"""Windows 特殊資料夾與本程式的設定／log 路徑。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "MyUsageMonitor"


def home() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home())


def roaming() -> Path:
    """%APPDATA%"""
    return Path(os.environ.get("APPDATA") or home() / "AppData" / "Roaming")


def local() -> Path:
    """%LOCALAPPDATA%"""
    return Path(os.environ.get("LOCALAPPDATA") or home() / "AppData" / "Local")


def app_dir() -> Path:
    return roaming() / APP_NAME


def settings_file() -> Path:
    return app_dir() / "settings.json"


def log_file() -> Path:
    return app_dir() / "monitor.log"


def app_icon_file() -> Path:
    """assets/app.ico：打包版在 PyInstaller 解壓目錄，開發版在 repo 根目錄。"""
    bundle = getattr(sys, "_MEIPASS", None)
    root = Path(bundle) if bundle else Path(__file__).resolve().parents[3]
    return root / "assets" / "app.ico"
