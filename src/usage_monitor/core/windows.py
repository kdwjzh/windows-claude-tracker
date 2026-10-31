"""用量週期長度 → 列標籤（CLAUDE.md §3.4）。"""

from __future__ import annotations

LONG_WINDOW_SECONDS = 86_400
"""週期長度大於等於一天就算長週期（7d／30d），不依賴 API 欄位順序。"""


def is_long_window(seconds: float | None) -> bool:
    return seconds is not None and seconds >= LONG_WINDOW_SECONDS


def label_for_seconds(seconds: float | None) -> str | None:
    """18000 → "5h"、604800 → "7d"、2592000 → "30d"；無法判斷時回傳 None。"""
    if seconds is None or seconds <= 0:
        return None
    if is_long_window(seconds):
        return f"{round(seconds / 86_400)}d"
    return f"{max(1, round(seconds / 3_600))}h"
