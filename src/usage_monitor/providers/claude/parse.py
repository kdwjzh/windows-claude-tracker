"""Claude 回應 → Usage（純函式）。API 未公開，欄位缺漏要寬容。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.json_access import (
    as_dict,
    as_float,
    as_list,
    as_str,
    parse_iso,
    parse_unix,
)
from usage_monitor.core.models import Usage, Window

SESSION_LABEL = "5h"
LONG_LABEL = "7d"

_H = "anthropic-ratelimit-unified-"


def _bucket_window(bucket: object, label: str) -> Window | None:
    """舊格式：`five_hour` / `seven_day` 物件，utilization 0–100。"""
    data = as_dict(bucket)
    percent = as_float((data or {}).get("utilization"))
    if data is None or percent is None:
        return None
    return Window(True, percent, parse_iso(data.get("resets_at")), label)


def _limits_window(limits: object, kind: str, label: str) -> Window | None:
    """新格式：`limits[]` 中 scope 為 null 的 session／weekly_all 項目。"""
    for raw in as_list(limits) or []:
        item = as_dict(raw)
        if item is None or as_str(item.get("kind")) != kind or item.get("scope") is not None:
            continue
        percent = as_float(item.get("percent"))
        if percent is None:
            percent = as_float(item.get("utilization"))
        if percent is not None:
            return Window(True, percent, parse_iso(item.get("resets_at")), label)
    return None


def parse_usage(body: object, fetched_at: datetime) -> Usage:
    """`/api/oauth/usage` 的 JSON → Usage；兩個視窗都沒有時丟 TRANSIENT。"""
    data = as_dict(body)
    if data is None:
        raise PollError(ErrKind.TRANSIENT, "用量 API 回應格式不認得", reason=ErrReason.BAD_RESPONSE)
    limits = data.get("limits")
    session = _bucket_window(data.get("five_hour"), SESSION_LABEL) or _limits_window(
        limits, "session", SESSION_LABEL
    )
    long = _bucket_window(data.get("seven_day"), LONG_LABEL) or _limits_window(
        limits, "weekly_all", LONG_LABEL
    )
    if session is None and long is None:
        raise PollError(
            ErrKind.TRANSIENT, "用量 API 回應中沒有任何用量視窗", reason=ErrReason.BAD_RESPONSE
        )
    return Usage(
        session=session or Window(label=SESSION_LABEL),
        long=long or Window(label=LONG_LABEL),
        fetched_at=fetched_at,
    )


def parse_headers(header: Callable[[str], str | None], fetched_at: datetime) -> Usage:
    """Messages API 的 rate-limit header → Usage。utilization 是 0–1，要 ×100。

    `status == rejected` 且兩個 utilization 都是 0 時，依 representative-claim 把對應視窗設為 100%。
    """

    def window(prefix: str, label: str) -> Window:
        fraction = as_float(header(f"{_H}{prefix}-utilization"))
        if fraction is None:
            return Window(label=label)
        return Window(True, fraction * 100, parse_unix(header(f"{_H}{prefix}-reset")), label)

    session = window("5h", SESSION_LABEL)
    long = window("7d", LONG_LABEL)

    rejected = (header(f"{_H}status") or "").strip() == "rejected"
    if rejected and session.percent == 0 and long.percent == 0:
        claim = (header(f"{_H}representative-claim") or "").strip()
        if claim == "five_hour":
            session = Window(True, 100.0, session.resets_at, SESSION_LABEL)
        elif claim == "seven_day":
            long = Window(True, 100.0, long.resets_at, LONG_LABEL)

    if not (session.available or long.available):
        raise PollError(
            ErrKind.TRANSIENT,
            "Messages API 的 header 中沒有任何用量視窗",
            reason=ErrReason.BAD_RESPONSE,
        )
    return Usage(session=session, long=long, fetched_at=fetched_at)
