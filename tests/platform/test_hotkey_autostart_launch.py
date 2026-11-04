from __future__ import annotations

import pytest

from usage_monitor.platform import autostart, fullscreen, hotkey, power


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
    assert power.is_resume_message(0) is False


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


class _Writes:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self) -> None:
        self.count += 1


def test_autostart_sync_rewrites_old_exe() -> None:
    write = _Writes()
    old = r'"C:\Apps\ClaudeUsageTracker-v1.2.0.exe"'
    assert autostart.sync_command(read=lambda: old, write=write) is True
    assert write.count == 1


def test_autostart_sync_keeps_current_command() -> None:
    write = _Writes()
    current = autostart.command().upper()  # Windows 路徑不分大小寫
    assert autostart.sync_command(read=lambda: current, write=write) is False
    assert write.count == 0


def test_autostart_sync_ignores_disabled() -> None:
    write = _Writes()
    assert autostart.sync_command(read=lambda: None, write=write) is False
    assert write.count == 0


def test_autostart_sync_write_failure_is_logged_not_raised() -> None:
    def fail() -> None:
        raise OSError("denied")

    assert autostart.sync_command(read=lambda: '"C:\\old.exe"', write=fail) is False


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
