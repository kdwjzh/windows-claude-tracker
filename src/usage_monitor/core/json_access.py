"""寬容地讀取未公開 API 的 JSON：欄位缺漏或型別不對時回傳 None，不丟例外。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast


def as_dict(value: object) -> dict[str, object] | None:
    return cast(dict[str, object], value) if isinstance(value, dict) else None


def as_list(value: object) -> list[object] | None:
    return cast(list[object], value) if isinstance(value, list) else None


def as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def as_float(value: object) -> float | None:
    """數字或數字字串 → float；bool 不算數字。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def parse_iso(value: object) -> datetime | None:
    """ISO 8601 → UTC aware；沒有時區的視為 UTC。"""
    text = as_str(value)
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def parse_unix(value: object) -> datetime | None:
    """Unix 秒 → UTC aware。"""
    secs = as_float(value)
    if secs is None or secs <= 0:
        return None
    try:
        return datetime.fromtimestamp(secs, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def parse_unix_ms(value: object) -> datetime | None:
    """Unix 毫秒 → UTC aware。"""
    ms = as_float(value)
    return parse_unix(ms / 1000) if ms is not None else None
