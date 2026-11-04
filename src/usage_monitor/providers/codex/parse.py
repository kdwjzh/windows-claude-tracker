"""Codex 回應 → Usage（純函式）。

`rate_limit.primary_window`／`secondary_window` 依 `limit_window_seconds` 判斷長短週期，
不依賴欄位順序；列標籤也依實際週期產生（18000 → 5h、604800 → 7d、約 30 天 → 30d）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.json_access import as_dict, as_float, parse_unix, unknown_keys
from usage_monitor.core.models import Usage, Window
from usage_monitor.core.windows import is_long_window, label_for_seconds

DEFAULT_SESSION_LABEL = "5h"
DEFAULT_LONG_LABEL = "7d"

log = logging.getLogger(__name__)

# 已知的欄位（2026-11 的實際回應）：不認得、值又不是 null 的欄位記一行 debug log（只記名稱）
KNOWN_KEYS = frozenset({
    "user_id", "account_id", "email", "plan_type", "rate_limit", "code_review_rate_limit",
    "additional_rate_limits", "model_usage", "credits", "spend_control",
    "rate_limit_reached_type", "promo", "rate_limit_reset_credits",
})  # fmt: skip
KNOWN_RATE_LIMIT_KEYS = frozenset(
    {"allowed", "limit_reached", "primary_window", "secondary_window"}
)
KNOWN_WINDOW_KEYS = frozenset(
    {"used_percent", "limit_window_seconds", "reset_after_seconds", "reset_at"}
)


def log_unknown(data: dict[str, object] | None) -> None:
    """不認得的欄位記一行 debug log（ROADMAP 第 14 項）。"""
    rate_limit = as_dict((data or {}).get("rate_limit"))
    found = unknown_keys(data, KNOWN_KEYS)
    found += [f"rate_limit.{k}" for k in unknown_keys(rate_limit, KNOWN_RATE_LIMIT_KEYS)]
    for name in ("primary_window", "secondary_window"):
        window = as_dict((rate_limit or {}).get(name))
        found += [f"{name}.{k}" for k in unknown_keys(window, KNOWN_WINDOW_KEYS)]
    if found:
        log.debug("Codex 用量 API 回應有不認得的欄位：%s", ", ".join(found))


def _window(raw: object, fetched_at: datetime) -> tuple[Window, float | None] | None:
    data = as_dict(raw)
    if data is None:
        return None
    percent = as_float(data.get("used_percent"))
    if percent is None:
        return None
    seconds = as_float(data.get("limit_window_seconds"))
    resets_at = parse_unix(data.get("reset_at"))
    if resets_at is None:
        after = as_float(data.get("reset_after_seconds"))
        if after is not None and after >= 0:
            resets_at = fetched_at + timedelta(seconds=after)
    return Window(True, percent, resets_at, label_for_seconds(seconds)), seconds


def parse_usage(body: object, fetched_at: datetime) -> Usage:
    log_unknown(as_dict(body))
    rate_limit = as_dict((as_dict(body) or {}).get("rate_limit"))
    if rate_limit is None:
        raise PollError(
            ErrKind.TRANSIENT, "Codex 用量 API 回應中沒有 rate_limit", reason=ErrReason.BAD_RESPONSE
        )

    session: Window | None = None
    long: Window | None = None
    for position, key in enumerate(("primary_window", "secondary_window")):
        parsed = _window(rate_limit.get(key), fetched_at)
        if parsed is None:
            continue
        window, seconds = parsed
        # 有週期長度就照長度分；沒有時才退回「primary 是短週期、secondary 是長週期」
        wants_long = is_long_window(seconds) if seconds is not None else position == 1
        # 想放的位置已被占用時放另一個（最多兩個視窗，不會兩個都滿）
        if wants_long and long is None:
            long = window
        elif session is None:
            session = window
        else:
            long = window

    if session is None and long is None:
        raise PollError(
            ErrKind.TRANSIENT,
            "Codex 用量 API 回應中沒有任何用量視窗",
            reason=ErrReason.BAD_RESPONSE,
        )
    session = session or Window()
    long = long or Window()
    return Usage(
        session=Window(
            session.available, session.percent, session.resets_at,
            session.label or DEFAULT_SESSION_LABEL,
        ),
        long=Window(
            long.available, long.percent, long.resets_at, long.label or DEFAULT_LONG_LABEL
        ),
        fetched_at=fetched_at,
    )  # fmt: skip
