from __future__ import annotations

from pathlib import Path

import pytest

from usage_monitor.platform import paths


def test_paths_follow_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert paths.home() == tmp_path / "home"
    assert paths.roaming() == tmp_path / "roaming"
    assert paths.local() == tmp_path / "local"
    assert paths.settings_file() == tmp_path / "roaming" / "MyUsageMonitor" / "settings.json"
    assert paths.log_file() == tmp_path / "roaming" / "MyUsageMonitor" / "monitor.log"


def test_paths_fallback_to_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert paths.roaming() == tmp_path / "AppData" / "Roaming"
    assert paths.local() == tmp_path / "AppData" / "Local"


def test_app_icon_file_in_repo() -> None:
    icon = paths.app_icon_file()
    assert icon.parts[-2:] == ("assets", "app.ico")
    assert icon.is_file()


def test_app_icon_file_when_frozen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
    assert paths.app_icon_file() == tmp_path / "assets" / "app.ico"
