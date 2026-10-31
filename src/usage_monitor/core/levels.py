"""百分比 → 顏色等級。門檻只寫在這裡，小工具與系統匣共用。"""

from __future__ import annotations

from enum import Enum

WARN_AT = 70.0
CRIT_AT = 90.0


class Level(Enum):
    OK = "ok"
    WARN = "warn"
    CRIT = "crit"


def level_of(percent: float) -> Level:
    if percent >= CRIT_AT:
        return Level.CRIT
    if percent >= WARN_AT:
        return Level.WARN
    return Level.OK
