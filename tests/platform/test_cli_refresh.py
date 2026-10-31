"""CLI token 更新（階段 7）：用假的 which／runner，不會真的執行 claude。"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from typing import Any

import pytest

from fakes import FakeClock
from usage_monitor.platform import cli_refresh
from usage_monitor.platform.cli_refresh import (
    CREATE_NO_WINDOW,
    ClaudeCliRefresher,
    find_claude,
    parse_version,
)

NOW = datetime(2026, 10, 30, 9, tzinfo=UTC)
EXE = r"C:\Users\me\.local\bin\claude.exe"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2.0.63 (Claude Code)", (2, 0, 63)),
        ("claude 2.1.7\n", (2, 1, 7)),
        ("10.20.30", (10, 20, 30)),
        ("no version", None),
        ("", None),
    ],
)
def test_parse_version(text: str, expected: tuple[int, int, int] | None) -> None:
    assert parse_version(text) == expected


def test_find_claude_prefers_cmd_and_wraps_it() -> None:
    found = {"claude.cmd": r"C:\npm\claude.cmd", "claude": EXE}
    assert find_claude(found.get) == ["cmd.exe", "/d", "/c", r"C:\npm\claude.cmd"]


def test_find_claude_exe_and_missing() -> None:
    assert find_claude({"claude": EXE}.get) == [EXE]
    assert find_claude({}.get) is None


class FakeRunner:
    """依序回傳排好的結果；BaseException 會被丟出。"""

    def __init__(self, *results: tuple[int, str] | BaseException) -> None:
        self.results = list(results)
        self.calls: list[tuple[list[str], float]] = []

    def __call__(self, cmd: list[str], timeout: float) -> tuple[int, str]:
        self.calls.append((cmd, timeout))
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def refresher(runner: FakeRunner, clock: FakeClock | None = None, found: bool = True):
    which = {"claude": EXE}.get if found else {}.get
    return ClaudeCliRefresher(clock or FakeClock(NOW), which=which, run=runner)


def test_success_checks_version_then_refreshes() -> None:
    runner = FakeRunner((0, "2.0.63 (Claude Code)"), (0, "ok"))
    assert refresher(runner)() is True
    assert [c for c, _ in runner.calls] == [
        [EXE, "--version"],
        [EXE, "-p", ".", "--no-session-persistence"],
    ]
    assert runner.calls[1][1] == cli_refresh.REFRESH_TIMEOUT


def test_at_most_once_per_30_minutes_and_version_cached() -> None:
    clock = FakeClock(NOW)
    runner = FakeRunner((0, "2.1.0"), (0, ""), (0, ""))
    r = refresher(runner, clock)
    assert r() is True
    clock.advance(minutes=29)
    assert r() is False  # 太快：不執行
    assert len(runner.calls) == 2
    clock.advance(minutes=1)
    assert r() is True
    assert runner.calls[-1][0][1:] == ["-p", ".", "--no-session-persistence"]  # 版本只檢查一次


def test_old_version_never_refreshes() -> None:
    clock = FakeClock(NOW)
    runner = FakeRunner((0, "2.0.62"))
    r = refresher(runner, clock)
    assert r() is False
    clock.advance(hours=1)
    assert r() is False  # 已知版本太舊，不再執行任何指令
    assert len(runner.calls) == 1


@pytest.mark.parametrize(
    "version_result",
    [(1, "error"), (0, "garbage"), subprocess.TimeoutExpired("claude", 15), OSError("x")],
)
def test_version_check_failures(version_result: tuple[int, str] | BaseException) -> None:
    runner = FakeRunner(version_result)
    assert refresher(runner)() is False
    assert len(runner.calls) == 1


def test_version_timeout_is_rechecked_later() -> None:
    clock = FakeClock(NOW)
    runner = FakeRunner(subprocess.TimeoutExpired("claude", 15), (0, "2.0.63"), (0, ""))
    r = refresher(runner, clock)
    assert r() is False
    clock.advance(minutes=30)
    assert r() is True


@pytest.mark.parametrize(
    "refresh_result",
    [(1, ""), subprocess.TimeoutExpired("claude", 90), FileNotFoundError("claude")],
)
def test_refresh_failures(refresh_result: tuple[int, str] | BaseException) -> None:
    runner = FakeRunner((0, "2.0.63"), refresh_result)
    assert refresher(runner)() is False


def test_missing_claude() -> None:
    runner = FakeRunner()
    assert refresher(runner, found=False)() is False
    assert runner.calls == []


def test_run_hidden_uses_no_window_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs, cmd=cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="2.0.63\n", stderr="")

    monkeypatch.setattr(cli_refresh.subprocess, "run", fake_run)
    assert cli_refresh.run_hidden([EXE, "--version"], 15) == (0, "2.0.63\n")
    assert seen["creationflags"] == CREATE_NO_WINDOW == 0x08000000
    assert seen["timeout"] == 15
    assert seen["stdin"] is subprocess.DEVNULL
    assert seen["check"] is False
