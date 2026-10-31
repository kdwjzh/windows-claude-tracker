"""真的呼叫 Win32：mutex、登錄檔讀取、前景視窗檢查。不改任何系統設定。"""

from __future__ import annotations

import uuid

import pytest

from usage_monitor.platform import autostart, fullscreen
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


def test_fullscreen_check_runs() -> None:
    assert isinstance(fullscreen.is_foreground_fullscreen(), bool)


def test_autostart_is_enabled_reads_registry() -> None:
    assert isinstance(autostart.is_enabled(), bool)
