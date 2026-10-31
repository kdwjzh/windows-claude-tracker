"""資料模型（CLAUDE.md §3.6）。全部 frozen：產生後不會被別的模組改掉。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from usage_monitor.core.errors import PollError


@dataclass(frozen=True)
class Window:
    """一個用量週期（例如 5 小時或 7 天）。"""

    available: bool = False
    """服務有回報這個視窗（0% 也算），與「沒資料」區分。"""
    percent: float = 0.0
    """0–100。"""
    resets_at: datetime | None = None
    """UTC aware。"""
    label: str | None = None
    """列標籤，如 "5h"、"7d"、"30d"；None 時由 UI 用預設。"""


@dataclass(frozen=True)
class Usage:
    session: Window
    """短週期（5h）。"""
    long: Window
    """長週期（7d／30d）。"""
    fetched_at: datetime
    """UTC aware。"""


@dataclass(frozen=True)
class ProviderState:
    """services 層維護，UI 只讀這個。"""

    provider_id: str
    usage: Usage | None
    """最後一次成功的資料。"""
    error: PollError | None
    """最後一次的錯誤；成功時為 None。"""
    stale: bool
    """usage 是舊的（最後一次輪詢失敗）。"""
    source_label: str | None
    """來源代碼 "desktop"／"cli"／"codex_cli"，畫面依語言翻譯；不含 token。"""
