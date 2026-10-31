from __future__ import annotations

import pytest

from usage_monitor.core.windows import is_long_window, label_for_seconds


@pytest.mark.parametrize(
    ("seconds", "label"),
    [
        (18_000, "5h"),
        (3_600, "1h"),
        (600, "1h"),
        (86_400, "1d"),
        (604_800, "7d"),
        (2_592_000, "30d"),
        (2_505_600, "29d"),
        (None, None),
        (0, None),
        (-5, None),
    ],
)
def test_label_for_seconds(seconds: float | None, label: str | None) -> None:
    assert label_for_seconds(seconds) == label


@pytest.mark.parametrize(
    ("seconds", "long"),
    [(18_000, False), (86_399, False), (86_400, True), (604_800, True), (None, False)],
)
def test_is_long_window(seconds: float | None, long: bool) -> None:
    assert is_long_window(seconds) is long
