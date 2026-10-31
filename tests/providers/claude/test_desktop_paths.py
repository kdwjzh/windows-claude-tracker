from __future__ import annotations

from pathlib import Path

import pytest

from usage_monitor.providers.claude.credentials.desktop_paths import data_dirs


def _mk(path: Path) -> Path:
    path.mkdir(parents=True)
    return path


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "Local", tmp_path / "Roaming"


def test_order_new_then_legacy_then_store(roots: tuple[Path, Path]) -> None:
    local, roaming = roots
    new_other = _mk(local / "Claude-Data" / "claude_aaaaaaaaaaaaa")
    new_preferred = _mk(local / "Claude-Data" / "claude_pzs8sxrjxfjjc")
    _mk(roaming / "Claude")
    pkg_other = _mk(local / "Packages" / "Claude_bbbbbbbbbbbbb")
    pkg_preferred = _mk(local / "Packages" / "Claude_pzs8sxrjxfjjc")

    assert data_dirs(local, roaming) == [
        new_preferred,
        new_other,
        roaming / "Claude",
        pkg_preferred / "LocalCache" / "Roaming" / "Claude",
        pkg_other / "LocalCache" / "Roaming" / "Claude",
    ]


def test_legacy_dir_listed_even_if_missing(roots: tuple[Path, Path]) -> None:
    local, roaming = roots
    assert data_dirs(local, roaming) == [roaming / "Claude"]


@pytest.mark.parametrize(
    "name",
    [
        "Claude_pzs8sxrjxfjjc",  # Claude-Data 底下要小寫
        "claude_PZS8SXRJXFJJC",  # publisher 要小寫
        "claude_pzs8sxrjxfjj",  # 12 碼
        "claude_pzs8sxrjxfjjcc",  # 14 碼
        "claude-pzs8sxrjxfjjc",
        "xclaude_pzs8sxrjxfjjc",
    ],
)
def test_new_dir_pattern_rejects(roots: tuple[Path, Path], name: str) -> None:
    local, roaming = roots
    _mk(local / "Claude-Data" / name)
    assert data_dirs(local, roaming) == [roaming / "Claude"]


@pytest.mark.parametrize("name", ["claude_pzs8sxrjxfjjc", "Claude_pzs8sxrjxfjj"])
def test_package_pattern_rejects(roots: tuple[Path, Path], name: str) -> None:
    local, roaming = roots
    _mk(local / "Packages" / name)  # Packages 底下要大寫 Claude_ 且 13 碼
    assert data_dirs(local, roaming) == [roaming / "Claude"]


def test_files_are_not_dirs(roots: tuple[Path, Path]) -> None:
    local, roaming = roots
    _mk(local / "Claude-Data")
    (local / "Claude-Data" / "claude_pzs8sxrjxfjjc").write_text("x")
    _mk(local / "Packages")
    (local / "Packages" / "Claude_pzs8sxrjxfjjc").write_text("x")
    assert data_dirs(local, roaming) == [roaming / "Claude"]


def test_defaults_use_platform_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "L"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "R"))
    new = _mk(tmp_path / "L" / "Claude-Data" / "claude_pzs8sxrjxfjjc")
    assert data_dirs() == [new, tmp_path / "R" / "Claude"]
