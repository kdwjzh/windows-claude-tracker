from __future__ import annotations

import pytest

from usage_monitor.core.levels import Level, level_of


@pytest.mark.parametrize(
    ("percent", "level"),
    [
        (0, Level.OK),
        (69.9, Level.OK),
        (70, Level.WARN),
        (89.9, Level.WARN),
        (90, Level.CRIT),
        (100, Level.CRIT),
        (130, Level.CRIT),
    ],
)
def test_level_of(percent: float, level: Level) -> None:
    assert level_of(percent) is level
