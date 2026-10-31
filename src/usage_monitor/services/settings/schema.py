"""設定的結構、預設值與驗證。

讀進來的 dict 逐欄寬容驗證：某個欄位壞掉只會讓「那個欄位」回到預設值並留下警告，
不會讓整份設定作廢。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from usage_monitor.core.i18n import LANGUAGE_CHOICES
from usage_monitor.core.json_access import as_dict, as_float, as_list, as_str

CURRENT_VERSION = 2
"""v2（0.10.0）：新增 update_check。"""

MIN_INTERVAL_MINUTES = 1
MAX_INTERVAL_MINUTES = 24 * 60
MIN_OPACITY = 0.3
THEMES = ("system", "dark", "light")


@dataclass(frozen=True)
class WidgetSettings:
    visible: bool = True
    locked: bool = False
    opacity: float = 0.9
    screen: str | None = None
    """螢幕名稱，例如 `\\\\.\\DISPLAY1`；None 表示用主螢幕預設位置。"""
    pos: tuple[int, int] | None = None
    """相對該螢幕工作區左上角的座標。"""
    hide_on_fullscreen: bool = True
    hotkey: str = "Ctrl+Alt+U"
    theme: str = "system"
    """"system"（跟隨 Windows）、"dark"、"light"。"""


@dataclass(frozen=True)
class UpdateCheckSettings:
    """更新檢查（CLAUDE.md §3.9）。"""

    enabled: bool = True
    """False 時只有在「關於」頁手動按「檢查更新」才會查。"""
    skipped_version: str | None = None
    """使用者按了「略過這個版本」的版本；更新的版本照常提醒。"""
    last_checked_at: str | None = None
    """最後一次成功連上 GitHub 的時間（ISO 8601，UTC）。"""
    notified_version: str | None = None
    """已經發過 Windows 通知的版本；每個新版本只通知一次。"""


@dataclass(frozen=True)
class Settings:
    schema_version: int = CURRENT_VERSION
    interval_minutes: int = 5
    providers: tuple[str, ...] = ("claude",)
    allow_cli_refresh: bool = False
    language: str = "system"
    """"system"（跟隨 Windows 顯示語言）、"zh-TW"、"en"（CLAUDE.md §3.8）。"""
    widget: WidgetSettings = field(default_factory=WidgetSettings)
    update_check: UpdateCheckSettings = field(default_factory=UpdateCheckSettings)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["providers"] = list(self.providers)
        pos = self.widget.pos
        data["widget"]["pos"] = list(pos) if pos is not None else None
        return data


class _Reader:
    """逐欄讀取並收集警告。"""

    def __init__(self, raw: Mapping[str, object], prefix: str, warnings: list[str]) -> None:
        self.raw = raw
        self.prefix = prefix
        self.warnings = warnings

    def _warn(self, key: str, value: object, default: object) -> None:
        self.warnings.append(f"設定 {self.prefix}{key}={value!r} 不正確，改用預設值 {default!r}")

    def boolean(self, key: str, default: bool) -> bool:
        value = self.raw.get(key, default)
        if isinstance(value, bool):
            return value
        self._warn(key, value, default)
        return default

    def text(self, key: str, default: str, choices: tuple[str, ...] = ()) -> str:
        value = self.raw.get(key, default)
        text = as_str(value)
        if text is not None and text.strip() and (not choices or text in choices):
            return text.strip()
        self._warn(key, value, default)
        return default

    def optional_text(self, key: str) -> str | None:
        value = self.raw.get(key)
        if value is None or (isinstance(value, str) and value.strip()):
            return value.strip() if isinstance(value, str) else None
        self._warn(key, value, None)
        return None

    def integer(self, key: str, default: int, lo: int, hi: int) -> int:
        value = self.raw.get(key, default)
        number = as_float(value) if not isinstance(value, str) else None
        if number is None or number != int(number):
            self._warn(key, value, default)
            return default
        clamped = min(max(int(number), lo), hi)
        if clamped != number:
            self.warnings.append(f"設定 {self.prefix}{key}={value!r} 超出範圍，改用 {clamped}")
        return clamped

    def ratio(self, key: str, default: float, lo: float, hi: float) -> float:
        value = self.raw.get(key, default)
        number = as_float(value) if not isinstance(value, str) else None
        if number is None:
            self._warn(key, value, default)
            return default
        clamped = min(max(number, lo), hi)
        if clamped != number:
            self.warnings.append(f"設定 {self.prefix}{key}={value!r} 超出範圍，改用 {clamped}")
        return clamped

    def point(self, key: str) -> tuple[int, int] | None:
        value = self.raw.get(key)
        if value is None:
            return None
        items = as_list(value)
        if items is not None and len(items) == 2:
            x, y = (as_float(v) if not isinstance(v, str) else None for v in items)
            if x is not None and y is not None:
                return int(x), int(y)
        self._warn(key, value, None)
        return None

    def names(self, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
        value = self.raw.get(key, list(default))
        items = as_list(value)
        if items is None or not all(isinstance(v, str) and v.strip() for v in items):
            self._warn(key, value, list(default))
            return default
        result: list[str] = []
        for v in items:
            name = str(v).strip()
            if name not in result:
                result.append(name)
        return tuple(result)


def _widget_from_dict(raw: object, warnings: list[str]) -> WidgetSettings:
    default = WidgetSettings()
    data = as_dict(raw)
    if data is None:
        if raw is not None:
            warnings.append(f"設定 widget={raw!r} 不正確，改用預設值")
        return default
    r = _Reader(data, "widget.", warnings)
    return WidgetSettings(
        visible=r.boolean("visible", default.visible),
        locked=r.boolean("locked", default.locked),
        opacity=r.ratio("opacity", default.opacity, MIN_OPACITY, 1.0),
        screen=r.optional_text("screen"),
        pos=r.point("pos"),
        hide_on_fullscreen=r.boolean("hide_on_fullscreen", default.hide_on_fullscreen),
        hotkey=r.text("hotkey", default.hotkey),
        theme=r.text("theme", default.theme, THEMES),
    )


def settings_from_dict(raw: Mapping[str, object]) -> tuple[Settings, list[str]]:
    """已遷移到目前版本的 dict → Settings；回傳 (設定, 警告訊息)。未知欄位直接忽略。"""
    warnings: list[str] = []
    default = Settings()
    r = _Reader(raw, "", warnings)
    settings = Settings(
        schema_version=CURRENT_VERSION,
        interval_minutes=r.integer(
            "interval_minutes", default.interval_minutes, MIN_INTERVAL_MINUTES, MAX_INTERVAL_MINUTES
        ),
        providers=r.names("providers", default.providers),
        allow_cli_refresh=r.boolean("allow_cli_refresh", default.allow_cli_refresh),
        language=r.text("language", default.language, LANGUAGE_CHOICES),
        widget=_widget_from_dict(raw.get("widget"), warnings),
        update_check=_update_check_from_dict(raw.get("update_check"), warnings),
    )
    return settings, warnings


def _update_check_from_dict(raw: object, warnings: list[str]) -> UpdateCheckSettings:
    default = UpdateCheckSettings()
    data = as_dict(raw)
    if data is None:
        if raw is not None:
            warnings.append(f"設定 update_check={raw!r} 不正確，改用預設值")
        return default
    r = _Reader(data, "update_check.", warnings)
    return UpdateCheckSettings(
        enabled=r.boolean("enabled", default.enabled),
        skipped_version=r.optional_text("skipped_version"),
        last_checked_at=r.optional_text("last_checked_at"),
        notified_version=r.optional_text("notified_version"),
    )
