"""桌面版 token cache 的 entry 解析與挑選（CLAUDE.md §3.2）。純函式。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

from usage_monitor.core.json_access import as_dict, as_float, as_str

INFERENCE = "user:inference"
PROFILE = "user:profile"


class Picked(NamedTuple):
    token: str
    expires_at_ms: float | None


def entry_scopes(entry_key: str) -> list[str]:
    """`<install>:<user>:<base url>:<scope1> <scope2> …` → scope 清單。

    第一段取「倒數第二個冒號之後」當第一個 scope（base url 本身含冒號），其餘各段是後續 scope。
    """
    words = entry_key.split()
    if not words:
        return []
    first = words[0]
    colons = [i for i, c in enumerate(first) if c == ":"]
    head = [first[colons[-2] + 1 :]] if len(colons) >= 2 else []
    return head + words[1:]


def select_token(entries: Mapping[str, object]) -> Picked | None:
    """挑最適合查用量的 token。

    排序（大者勝）：(同時有 inference 與 profile, 有 inference, expiresAt)。
    空 token、格式不對的 entry 直接略過。
    """
    best: tuple[tuple[bool, bool, float], Picked] | None = None
    for key, raw in entries.items():
        entry = as_dict(raw)
        if entry is None:
            continue
        token = (as_str(entry.get("token")) or "").strip()
        if not token:
            continue
        scopes = entry_scopes(key)
        inference = INFERENCE in scopes
        expires = as_float(entry.get("expiresAt"))
        rank = (inference and PROFILE in scopes, inference, expires if expires is not None else -1)
        if best is None or rank > best[0]:
            best = (rank, Picked(token, expires))
    return best[1] if best else None
