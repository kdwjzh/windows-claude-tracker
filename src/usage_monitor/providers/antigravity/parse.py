"""Antigravity 回應 → Usage（純函式，CLAUDE.md §3.10）。

`RetrieveUserQuotaSummary`：`response.groups[]` 是共用額度的模型分組（例如 Gemini、Claude 和 GPT），
每組的 `buckets[]` 有 `window`（"5h"／"weekly"）、`remainingFraction`（**剩餘** 0–1）、`resetTime`。
短／長週期取所有分組中用量最高的；每個分組的每個週期另外放進 `Usage.scoped`。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.json_access import as_dict, as_float, as_list, as_str, parse_iso
from usage_monitor.core.models import Usage, Window

log = logging.getLogger(__name__)

SESSION_LABEL = "5h"
LONG_LABEL = "7d"
_WINDOWS = {"5h": SESSION_LABEL, "weekly": LONG_LABEL}
_TIER = re.compile(r"^g1-([a-z0-9-]+?)-tier$")


def group_label(group: dict[str, object]) -> str | None:
    """分組的短名稱（小工具標籤欄很窄）。

    Gemini → "Gem"，Claude 和 GPT → "C/G"（維護者 2026-11-23 決定），其他取名稱第一個字。
    """
    name = (as_str(group.get("displayName")) or "").strip()
    ids = " ".join(
        as_str((as_dict(b) or {}).get("bucketId")) or ""
        for b in as_list(group.get("buckets")) or []
    ).lower()
    text = f"{name} {ids}".lower()
    if "claude" in text or "gpt" in text or " 3p-" in f" {ids}":
        return "C/G"
    if "gemini" in text:
        return "Gem"
    return name.split()[0] if name else None


def bucket_label(group_name: str | None, bucket: object) -> str | None:
    """Pro 方案的 Gemini 分組裡可能有獨立額度的 argon／carbon 桶。

    用它自己的名字，不跟 Gem 混在一起。
    """
    bucket_id = (as_str((as_dict(bucket) or {}).get("bucketId")) or "").lower()
    for special in ("argon", "carbon"):
        if bucket_id.startswith(special):
            return special.capitalize()
    return group_name


def _bucket(raw: object, fetched_at: datetime) -> tuple[str, Window] | None:
    """(週期標籤, Window)；不認得的週期或沒有數字時 None。"""
    data = as_dict(raw)
    if data is None:
        return None
    period = _WINDOWS.get((as_str(data.get("window")) or "").strip().lower())
    if period is None:
        return None
    resets_at = parse_iso(data.get("resetTime"))
    remaining = as_float(data.get("remainingFraction"))
    if remaining is None:
        # proto3 省略零值：額度用完時沒有 remainingFraction，只剩未來的 resetTime
        if resets_at is None or resets_at <= fetched_at:
            return None
        remaining = 0.0
    percent = (1.0 - min(1.0, max(0.0, remaining))) * 100
    return period, Window(True, percent, resets_at, period)


def _highest(windows: list[Window], label: str) -> Window:
    if not windows:
        return Window(label=label)
    top = max(windows, key=lambda w: w.percent)
    return Window(True, top.percent, top.resets_at, label)


def parse_usage(body: object, fetched_at: datetime) -> Usage:
    root = as_dict(body) or {}
    data = as_dict(root.get("response")) or root
    groups = [g for g in (as_dict(x) for x in as_list(data.get("groups")) or []) if g is not None]

    found: list[tuple[str, str, Window]] = []  # (分組短名, 週期, Window)
    for group in groups:
        group_name = group_label(group)
        for raw in as_list(group.get("buckets")) or []:
            name = bucket_label(group_name, raw)
            parsed = _bucket(raw, fetched_at)
            if parsed is not None and name is not None:
                found.append((name, *parsed))
    if not found:
        raise PollError(
            ErrKind.TRANSIENT,
            "Antigravity 配額摘要中沒有任何用量週期",
            reason=ErrReason.BAD_RESPONSE,
        )

    has_session = any(period == SESSION_LABEL for _, period, _ in found)
    # 只有週限制時標籤就是分組名稱（小工具一列一組）；有 5h 時加上週期以便分辨
    scoped = tuple(
        Window(True, w.percent, w.resets_at, f"{name} {period}" if has_session else name)
        for name, period, w in found
    )
    return Usage(
        session=_highest([w for _, p, w in found if p == SESSION_LABEL], SESSION_LABEL),
        long=_highest([w for _, p, w in found if p == LONG_LABEL], LONG_LABEL),
        fetched_at=fetched_at,
        scoped=scoped,
    )


def parse_plan(body: object) -> str | None:
    """`GetUserStatus` → 方案名稱。只讀 `userTier.id`（"g1-plus-tier" → "Plus"）。

    同一個回應裡有 email 和名字，**絕不讀取**；
    `planInfo.planName` 是舊欄位（Plus 帳號也是 "Pro"），不用。
    """
    user = as_dict((as_dict(body) or {}).get("userStatus"))
    tier = as_dict((user or {}).get("userTier"))
    match = _TIER.match((as_str((tier or {}).get("id")) or "").strip().lower())
    if match is None:
        return None
    return " ".join(part.capitalize() for part in match.group(1).split("-"))
