"""真的呼叫 Win32：mutex、登錄檔讀取、前景視窗檢查。不改任何系統設定。"""

from __future__ import annotations

import ctypes
import threading
import uuid

import pytest

from usage_monitor.platform import autostart, fullscreen, power
from usage_monitor.platform.single_instance import SingleInstance

pytestmark = pytest.mark.windows


def test_single_instance_blocks_second_copy() -> None:
    name = f"Local\\UsageMonitorTest_{uuid.uuid4().hex}"
    first, second = SingleInstance(name), SingleInstance(name)
    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()
    third = SingleInstance(name)
    assert third.acquire() is True
    third.release()


def test_single_instance_waits_for_previous_copy() -> None:
    """「立即更新」：新版等舊版放掉 mutex 才接手。"""
    name = f"Local\\UsageMonitorTest_{uuid.uuid4().hex}"
    old, new = SingleInstance(name), SingleInstance(name)
    assert old.acquire() is True
    assert new.acquire(wait=0.3) is False  # 舊版還在：等不到就放棄
    threading.Timer(0.3, old.release).start()
    assert new.acquire(wait=5) is True
    new.release()


def test_fullscreen_check_runs() -> None:
    assert isinstance(fullscreen.is_foreground_fullscreen(), bool)


def test_autostart_is_enabled_reads_registry() -> None:
    assert isinstance(autostart.is_enabled(), bool)


@pytest.mark.parametrize(
    ("message", "wparam", "expected"),
    [
        (power.WM_POWERBROADCAST, power.PBT_APMRESUMEAUTOMATIC, True),
        (power.WM_POWERBROADCAST, 0x0004, False),  # PBT_APMSUSPEND：要睡了，不是醒來
        (0x0312, power.PBT_APMRESUMEAUTOMATIC, False),
    ],
)
def test_is_resume_message(message: int, wparam: int, expected: bool) -> None:
    from ctypes import wintypes

    msg = wintypes.MSG(None, message, wparam, 0)
    assert power.is_resume_message(ctypes.addressof(msg)) is expected
