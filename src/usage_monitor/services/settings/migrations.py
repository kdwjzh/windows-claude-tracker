"""設定檔版本遷移：v0 → v1 → …。

新增欄位通常不需要遷移（缺的欄位會用預設值）；只有改名、改格式、改語意時才加遷移函式。
每個函式只負責「從 N 升到 N+1」，輸入輸出都是 dict，不可修改輸入。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from usage_monitor.services.settings.schema import CURRENT_VERSION

Migration = Callable[[dict[str, object]], dict[str, object]]


def _v0_to_v1(data: dict[str, object]) -> dict[str, object]:
    """v0：實作指南時期沒有 schema_version 的設定檔；欄位相同，只補上版本號。"""
    return {**data, "schema_version": 1}


def _v1_to_v2(data: dict[str, object]) -> dict[str, object]:
    """v2：新增 update_check（自動檢查更新預設開啟）。已經有的話保留使用者的值。"""
    if "update_check" in data:
        return dict(data)
    return {
        **data,
        "update_check": {
            "enabled": True,
            "skipped_version": None,
            "last_checked_at": None,
            "notified_version": None,
        },
    }


MIGRATIONS: dict[int, Migration] = {
    0: _v0_to_v1,
    1: _v1_to_v2,
}


class FutureVersionError(Exception):
    """設定檔比程式新（例如降版執行）。"""


def version_of(data: Mapping[str, object]) -> int:
    value = data.get("schema_version", 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def migrate(
    data: Mapping[str, object],
    *,
    target: int = CURRENT_VERSION,
    migrations: Mapping[int, Migration] = MIGRATIONS,
) -> dict[str, object]:
    """把 dict 升到 `target` 版。缺少某一步遷移時丟 KeyError（程式寫錯）。"""
    version = version_of(data)
    if version > target:
        raise FutureVersionError(f"設定檔版本 {version} 比程式支援的 {target} 新")
    result = dict(data)
    while version < target:
        result = migrations[version](result)
        version += 1
        result["schema_version"] = version
    return result
