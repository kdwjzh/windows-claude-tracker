"""真的呼叫 SetCurrentProcessExplicitAppUserModelID，再讀回來比對。"""

from __future__ import annotations

import ctypes

import pytest

from usage_monitor.core.app_info import APP_USER_MODEL_ID
from usage_monitor.platform import app_identity

pytestmark = pytest.mark.windows


def test_real_app_user_model_id() -> None:
    assert app_identity.apply() is True
    out = ctypes.c_wchar_p()
    assert ctypes.windll.shell32.GetCurrentProcessExplicitAppUserModelID(ctypes.byref(out)) == 0
    assert out.value == APP_USER_MODEL_ID
    ctypes.windll.ole32.CoTaskMemFree(out)
