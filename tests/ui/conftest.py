from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _english_windows(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Qt 測試一律假設 Windows 顯示語言是英文（跟 GitHub Actions 的 runner 一樣）。

    2026-10-30 bug：測試假設介面是中文，在中文 Windows 上會過、在英文的 CI runner 上會失敗。
    需要中文的測試必須自己把設定 language 設成 "zh-TW"，結果才不會因機器而異。
    只對 qt 測試生效：非 Qt 環境（ubuntu CI）不能 import controller。
    """
    if request.node.get_closest_marker("qt") is None:
        return
    monkeypatch.setattr("usage_monitor.ui.controller.system_ui_languages", lambda: ["en-US", "en"])
