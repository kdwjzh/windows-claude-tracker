"""Claude 回應 → Usage（純函式）。API 未公開，欄位缺漏要寬容。"""

from __future__ import annotations

import logging
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
    unknown_keys,
)
from usage_monitor.core.models import Usage, Window

log = logging.getLogger(__name__)

SESSION_LABEL = "5h"
LONG_LABEL = "7d"

_H = "anthropic-ratelimit-unified-"

# 已知的欄位（2026-11 的實際回應）：出現不在這裡、值又不是 null 的欄位時記一行 debug log，
# 方便發現 API 改版（只記欄位名稱，不記值）。沒用到的欄位（例如 spend）也列在這裡，避免雜訊。
KNOWN_KEYS = frozenset({
    "five_hour", "seven_day", "limits", "extra_usage", "spend", "seven_day_breakdown",
    "member_dashboard_available", "seven_day_opus", "seven_day_sonnet", "seven_day_oauth_apps",
    "seven_day_cowork", "weekly_scoped_shares",
})  # fmt: skip
KNOWN_BUCKET_KEYS = frozenset({
    "utilization", "resets_at", "limit_dollars", "used_dollars", "remaining_dollars",
    "locked_reason",
})  # fmt: skip
KNOWN_LIMIT_KEYS = frozenset(
    {"kind", "group", "percent", "utilization", "severity", "resets_at", "scope", "is_active"}
)
KNOWN_LIMIT_KINDS = frozenset({"session", "weekly_all", "weekly_scoped"})


def _bucket_window(bucket: object, label: str) -> Window | None:
    """舊格式：`five_hour` / `seven_day` 物件，utilization 0–100。"""
    data = as_dict(bucket)
    percent = as_float((data or {}).get("utilization"))
    if data is None or percent is None:
        return None
    return Window(True, percent, parse_iso(data.get("resets_at")), label)


def _limit_percent(item: dict[str, object]) -> float | None:
    percent = as_float(item.get("percent"))
    return percent if percent is not None else as_float(item.get("utilization"))


def _limits_window(limits: object, kind: str, label: str) -> Window | None:
    """新格式：`limits[]` 中 scope 為 null 的 session／weekly_all 項目。"""
    for raw in as_list(limits) or []:
        item = as_dict(raw)
        if item is None or as_str(item.get("kind")) != kind or item.get("scope") is not None:
            continue
        percent = _limit_percent(item)
        if percent is not None:
            return Window(True, percent, parse_iso(item.get("resets_at")), label)
    return None


def _scoped_windows(data: dict[str, object]) -> tuple[Window, ...]:
    """`limits[]` 裡每個 weekly_scoped 項目（模型專屬的每週限制，例如 Fable）。

    名稱用 `scope.model.display_name`，所以之後出現的新模型不用改程式就會顯示；
    `weekly_scoped_shares[].limit_index` 指向 limits[] 的位置，帶出「最多可用每週上限的幾 %」。
    """
    shares: dict[int, float] = {}
    for raw in as_list(data.get("weekly_scoped_shares")) or []:
        share = as_dict(raw) or {}
        index, allowance = (
            share.get("limit_index"),
            as_float(share.get("allowance_percent_of_weekly")),
        )
        if isinstance(index, int) and allowance is not None:
            shares[index] = allowance
    result: list[Window] = []
    for i, raw in enumerate(as_list(data.get("limits")) or []):
        item = as_dict(raw)
        if item is None or as_str(item.get("kind")) != "weekly_scoped":
            continue
        model = as_dict((as_dict(item.get("scope")) or {}).get("model")) or {}
        name, percent = as_str(model.get("display_name")), _limit_percent(item)
        if name and percent is not None:
            result.append(
                Window(True, percent, parse_iso(item.get("resets_at")), name, shares.get(i))
            )
    return tuple(result)


def log_unknown(data: dict[str, object]) -> None:
    """不認得的欄位與 limits[].kind 各記一行 debug log（ROADMAP 第 14 項）。"""
    found = [*unknown_keys(data, KNOWN_KEYS)]
    for name in ("five_hour", "seven_day"):
        found += [f"{name}.{k}" for k in unknown_keys(as_dict(data.get(name)), KNOWN_BUCKET_KEYS)]
    kinds: set[str] = set()
    for raw in as_list(data.get("limits")) or []:
        item = as_dict(raw)
        found += [f"limits[].{k}" for k in unknown_keys(item, KNOWN_LIMIT_KEYS)]
        kind = as_str((item or {}).get("kind"))
        if kind and kind not in KNOWN_LIMIT_KINDS:
            kinds.add(kind)
    if found:
        log.debug("用量 API 回應有不認得的欄位：%s", ", ".join(sorted(set(found))))
    if kinds:
        log.debug("用量 API 的 limits[] 有不認得的 kind：%s", ", ".join(sorted(kinds)))


def parse_usage(body: object, fetched_at: datetime) -> Usage:
    """`/api/oauth/usage` 的 JSON → Usage；兩個視窗都沒有時丟 TRANSIENT。"""
    data = as_dict(body)
    if data is None:
        raise PollError(ErrKind.TRANSIENT, "用量 API 回應格式不認得", reason=ErrReason.BAD_RESPONSE)
    log_unknown(data)
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
        scoped=_scoped_windows(data),
    )


_PLANS = {"claude_pro": "Pro", "claude_max": "Max", "claude_team": "Team",
          "claude_enterprise": "Enterprise"}  # fmt: skip
_MAX_TIERS = {"max_5x": "Max 5x", "max_20x": "Max 20x"}


def parse_plan(body: object) -> str | None:
    """`/api/oauth/profile` → 方案名稱。只讀 organization 的兩個方案欄位，其他（email 等）不碰。

    organization_type：claude_pro／claude_max／…；Max 再用 rate_limit_tier 分 5x／20x。
    不認得的 claude_xxx 顯示成 "Xxx"。
    """
    org = as_dict((as_dict(body) or {}).get("organization")) or {}
    kind = as_str(org.get("organization_type"))
    if not kind:
        return None
    name = _PLANS.get(kind) or kind.removeprefix("claude_").replace("_", " ").capitalize()
    if kind == "claude_max":
        tier = as_str(org.get("rate_limit_tier")) or ""
        name = next((v for k, v in _MAX_TIERS.items() if tier.endswith(k)), name)
    return name or None


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
