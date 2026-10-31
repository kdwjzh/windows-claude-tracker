from __future__ import annotations

import os
from pathlib import Path

import pytest

from usage_monitor.platform import autostart, fullscreen, hotkey, launch


@pytest.mark.parametrize(
    ("text", "mods", "vk"),
    [
        ("Ctrl+Alt+U", hotkey.MOD_CONTROL | hotkey.MOD_ALT, ord("U")),
        ("ctrl + shift + 5", hotkey.MOD_CONTROL | hotkey.MOD_SHIFT, ord("5")),
        ("Win+F12", hotkey.MOD_WIN, 0x7B),
        ("Alt+f1", hotkey.MOD_ALT, 0x70),
        ("Control+Alt+Shift+Win+Z", 0x000F, ord("Z")),
    ],
)
def test_parse_hotkey(text: str, mods: int, vk: int) -> None:
    assert hotkey.parse(text) == (mods | hotkey.MOD_NOREPEAT, vk)


@pytest.mark.parametrize(
    "text", ["", "U", "Ctrl+", "Hyper+U", "Ctrl+Alt+Enter", "Ctrl+F25", "Ctrl+é"]
)
def test_parse_hotkey_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        hotkey.parse(text)


def test_register_rejects_bad_hotkey_without_raising() -> None:
    assert hotkey.register(0, 1, "nonsense") is False


def test_is_hotkey_message_null_pointer() -> None:
    assert hotkey.is_hotkey_message(0, 1) is False


def test_autostart_command_source() -> None:
    cmd = autostart.command(r"C:\venv\Scripts\python.exe", frozen=False)
    assert cmd == r'"C:\venv\Scripts\pythonw.exe" -m usage_monitor'
    assert autostart.command(r"C:\venv\Scripts\pythonw.exe", frozen=False).startswith(
        r'"C:\venv\Scripts\pythonw.exe"'
    )


def test_autostart_command_frozen() -> None:
    assert autostart.command(r"C:\Apps\UsageMonitor.exe", frozen=True) == (
        r'"C:\Apps\UsageMonitor.exe"'
    )


def test_diagnose_command() -> None:
    assert launch.diagnose_command(r"C:\venv\Scripts\pythonw.exe", frozen=False) == [
        r"C:\venv\Scripts\python.exe",
        "-m",
        "usage_monitor.diagnose",
    ]
    assert launch.diagnose_command(
        r"C:\Apps\UsageMonitor.exe", frozen=True, find=lambda _: None
    ) == [r"C:\Apps\diagnose.exe"]


def test_diagnose_command_uses_found_exe(tmp_path: Path) -> None:
    found = tmp_path / "diagnose-v0.9.0.exe"
    cmd = launch.diagnose_command(r"C:\Apps\ClaudeUsageTracker-v0.9.0.exe", frozen=True,
                                  find=lambda _: found)  # fmt: skip
    assert cmd == [str(found)]


def test_find_diagnose_exe_prefers_plain_then_newest_versioned(tmp_path: Path) -> None:
    assert launch.find_diagnose_exe(tmp_path) is None
    old = tmp_path / "diagnose-v0.8.0.exe"
    new = tmp_path / "diagnose-v0.9.0.exe"
    old.write_bytes(b"")
    new.write_bytes(b"")
    os.utime(old, (1_000, 1_000))
    os.utime(new, (2_000, 2_000))
    (tmp_path / "diagnose-v1.0.0.exe").mkdir()  # 資料夾不算
    assert launch.find_diagnose_exe(tmp_path) == new
    plain = tmp_path / "diagnose.exe"
    plain.write_bytes(b"")
    assert launch.find_diagnose_exe(tmp_path) == plain


@pytest.mark.parametrize(
    ("window", "expected"),
    [
        ((0, 0, 1920, 1080), True),  # 剛好蓋滿
        ((-8, -8, 1928, 1088), True),  # 無邊框遊戲常見的超出
        ((0, 0, 1920, 1040), False),  # 最大化（工作列還在）
        ((100, 100, 800, 600), False),
    ],
)
def test_fullscreen_covers(window: tuple[int, int, int, int], expected: bool) -> None:
    assert fullscreen.covers(window, (0, 0, 1920, 1080)) is expected
