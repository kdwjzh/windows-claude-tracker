from __future__ import annotations

import os

from usage_monitor.platform.process import is_running


def test_current_process_is_running() -> None:
    assert is_running(os.getpid())


def test_invalid_or_finished_pid() -> None:
    assert not is_running(0)
    assert not is_running(-1)
    assert not is_running(2**31 - 1)  # 遠超過 Windows／Linux 的 pid 上限
