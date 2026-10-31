from __future__ import annotations

import logging
from typing import Any

import pytest

from usage_monitor.core.app_info import APP_USER_MODEL_ID
from usage_monitor.platform import app_identity


class FakeShell32:
    def __init__(self, result: int | Exception) -> None:
        self.result = result
        self.calls: list[str] = []

    def SetCurrentProcessExplicitAppUserModelID(self, app_id: Any) -> int:  # noqa: N802 - Win32 名稱
        self.calls.append(app_id.value)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_identity, "_failure", None)


def test_success_sets_id(caplog: pytest.LogCaptureFixture) -> None:
    shell = FakeShell32(0)
    assert app_identity.apply(shell32=shell) is True
    assert shell.calls == [APP_USER_MODEL_ID]
    app_identity.report()
    assert not caplog.records


@pytest.mark.parametrize(
    ("result", "expected"), [(-2147024809, "0x80070057"), (OSError("boom"), "OSError: boom")]
)
def test_failure_is_logged_not_raised(
    result: int | Exception, expected: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    assert app_identity.apply(shell32=FakeShell32(result)) is False
    caplog.clear()
    app_identity.report()  # log 設定好之後補記
    assert expected in caplog.text


def test_non_windows_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    assert app_identity.apply() is False
