"""「立即更新」的交接：參數解析、只刪安全的舊檔、刪不掉時重試。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from usage_monitor.platform import relaunch

OLD = "ClaudeUsageTracker-v1.3.0.exe"
NEW = "ClaudeUsageTracker-v2.0.0.exe"


def test_replaced_path() -> None:
    assert relaunch.replaced_path(["app.exe", "--replaced", r"D:\a\old.exe"]) == Path(
        r"D:\a\old.exe"
    )
    assert relaunch.replaced_path(["app.exe"]) is None
    assert relaunch.replaced_path(["app.exe", "--replaced"]) is None


def files(tmp_path: Path, old_name: str = OLD) -> tuple[Path, Path]:
    old, new = tmp_path / old_name, tmp_path / NEW
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    return old, new


def test_removes_old_exe(tmp_path: Path) -> None:
    old, new = files(tmp_path)
    assert relaunch.remove_replaced(old, new) is True
    assert not old.exists() and new.exists()


def test_already_gone_counts_as_done(tmp_path: Path) -> None:
    assert relaunch.remove_replaced(tmp_path / OLD, tmp_path / NEW) is True


@pytest.mark.parametrize("old_name", ["notes.txt", "Other.exe", "ClaudeUsageTracker.dll"])
def test_never_removes_files_that_are_not_ours(tmp_path: Path, old_name: str) -> None:
    old, new = files(tmp_path, old_name)
    assert relaunch.remove_replaced(old, new) is False
    assert old.exists()


def test_never_removes_from_another_folder(tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    old = other / OLD
    old.write_bytes(b"old")
    assert relaunch.remove_replaced(old, tmp_path / NEW) is False
    assert old.exists()


def test_never_removes_itself(tmp_path: Path) -> None:
    _old, new = files(tmp_path)
    assert relaunch.remove_replaced(new, new) is False
    assert new.exists()


def test_retries_while_locked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old, new = files(tmp_path)
    real_unlink = Path.unlink
    tries: list[int] = []

    def flaky(self: Path, missing_ok: bool = False) -> None:
        tries.append(1)
        if len(tries) < 3:
            raise PermissionError("in use")
        real_unlink(self)

    monkeypatch.setattr(Path, "unlink", flaky)
    slept: list[float] = []
    assert relaunch.remove_replaced(old, new, sleep=slept.append) is True
    assert len(tries) == 3 and slept == [0.5, 0.5]


def test_gives_up_after_attempts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old, new = files(tmp_path)

    def locked(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("in use")

    monkeypatch.setattr(Path, "unlink", locked)
    assert relaunch.remove_replaced(old, new, attempts=3, sleep=lambda _s: None) is False


def test_start_replacement_passes_old_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr(relaunch.subprocess, "Popen", lambda args, **kw: calls.append((args, kw)))
    relaunch.start_replacement(tmp_path / NEW, tmp_path / OLD)
    ((args, kw),) = calls
    assert args == [str(tmp_path / NEW), "--replaced", str(tmp_path / OLD)]
    assert kw["creationflags"] & relaunch.CREATE_NO_WINDOW
    assert kw["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


def test_frozen_exe_is_none_from_source() -> None:
    assert relaunch.frozen_exe() is None
