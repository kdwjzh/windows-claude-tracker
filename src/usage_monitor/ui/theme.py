"""第一版 UI 的所有顏色與尺寸（CLAUDE.md §3.7）。數值只寫在這裡。

尺寸單位是 Qt 的邏輯像素；Windows 縮放（125%、150%）由 Qt 自動處理。
"""

from __future__ import annotations

from dataclasses import dataclass

from usage_monitor.core.levels import Level


@dataclass(frozen=True)
class Palette:
    bg: str
    border: str
    handle: str
    divider: str
    text: str
    text_secondary: str
    text_dim: str
    seg_empty: str
    seg_error: str
    ok: str
    warn: str
    crit: str
    stale_ok: str
    stale_warn: str
    stale_crit: str
    error_text: str
    error_mark: str
    drag_border: str

    def level_color(self, level: Level, *, stale: bool = False) -> str:
        if stale:
            return {Level.OK: self.stale_ok, Level.WARN: self.stale_warn}.get(
                level, self.stale_crit
            )
        return {Level.OK: self.ok, Level.WARN: self.warn}.get(level, self.crit)


DARK = Palette(
    bg="#232428",
    border="#3a3c42",
    handle="#5b5f67",
    divider="#3a3c42",
    text="#e6e6e6",
    text_secondary="#a0a4ab",
    text_dim="#7c8088",
    seg_empty="#3b3e45",
    seg_error="#4a4d55",
    ok="#35c27a",
    warn="#f0b232",
    crit="#f05a46",
    stale_ok="#5f7d6c",
    stale_warn="#8a7a52",
    stale_crit="#8a5a52",
    error_text="#f08b7d",
    error_mark="#f05a46",
    drag_border="#7fb3ff",
)

LIGHT = Palette(
    bg="#f3f3f3",
    border="#d4d6db",
    handle="#a0a4ab",
    divider="#d4d6db",
    text="#1f1f1f",
    text_secondary="#5f6368",
    text_dim="#9aa0a6",
    seg_empty="#d9dbe0",
    seg_error="#c4c7cc",
    ok="#2fb36f",
    warn="#e0a21f",
    crit="#e0483a",
    stale_ok="#9cb5a6",
    stale_warn="#cdbb8e",
    stale_crit="#cf9d95",
    error_text="#c5221f",
    error_mark="#e0483a",
    drag_border="#3b82f6",
)


@dataclass(frozen=True)
class Metrics:
    radius: int = 8
    border: int = 1
    handle_w: int = 3
    handle_pad_l: int = 10
    handle_pad_r: int = 10
    pad_r: int = 8
    pad_t: int = 7
    pad_b: int = 8
    title_h: int = 16
    title_px: int = 11
    row_h: int = 19
    row_px: int = 12
    label_w: int = 24
    """週期標籤的最小寬度；「30d」這類較寬的標籤會依實際寬度＋label_gap 撐開。"""
    label_gap: int = 5
    segments: int = 10
    seg_w: int = 8
    seg_h: int = 14
    seg_gap: int = 2
    seg_radius: int = 2
    bar_text_gap: int = 6
    text_slack: int = 4
    """文字後面留的空隙：欄寬 = 這一欄目前最長文字的實際寬度＋這個值（不貼齊邊框）。"""
    col_gap: int = 12
    """兩欄之間（分隔線兩側各一半）。"""

    @property
    def bar_w(self) -> int:
        return self.segments * self.seg_w + (self.segments - 1) * self.seg_gap


METRICS = Metrics()

FONT_FAMILIES = ["Microsoft JhengHei UI", "Segoe UI"]

DIALOG_FONT_FAMILIES_ZH = ["Microsoft JhengHei", "Segoe UI"]
"""設定視窗在繁體中文時用微軟正黑體；英文沿用 FONT_FAMILIES。"""
DIALOG_FONT_WEIGHT = 700
"""設定視窗所有文字都用粗體（中英文皆同）。"""


@dataclass(frozen=True)
class DialogPalette:
    """設定視窗（畫板 5，Windows 11 風格）。"""

    window: str
    nav_selected: str
    card: str
    card_border: str
    control: str
    control_border: str
    text: str
    text_secondary: str
    accent: str
    """開關、滑桿、導覽列選取標記。"""
    accent_text: str
    switch_off_border: str
    ok_text: str
    error_text: str


DIALOG_DARK = DialogPalette(
    window="#202020",
    nav_selected="#2d2d2d",
    card="#2b2b2b",
    card_border="#333333",
    control="#2d2d2d",
    control_border="#454545",
    text="#e6e6e6",
    text_secondary="#a0a4ab",
    accent="#7fb3ff",
    accent_text="#10213a",
    switch_off_border="#9aa0a6",
    ok_text="#5fd39a",
    error_text="#f08b7d",
)

DIALOG_LIGHT = DialogPalette(
    window="#f3f3f3",
    nav_selected="#e9e9e9",
    card="#ffffff",
    card_border="#e5e5e5",
    control="#fbfbfb",
    control_border="#d1d1d1",
    text="#1f1f1f",
    text_secondary="#5f6368",
    accent="#0067c0",
    accent_text="#ffffff",
    switch_off_border="#868686",
    ok_text="#0f7b3f",
    error_text="#c5221f",
)

INTERVAL_CHOICES = (1, 2, 5, 10, 15, 30, 60)
"""設定視窗「更新間隔」的選項（分鐘）。"""

# 系統匣圖示（64×64 畫好再交給 Windows 縮小）
TRAY_SIZE = 64
TRAY_BG = "#2b2d31"
TRAY_TRACK = "#4a4d55"
TRAY_DOT_RED = "#f05a46"
TRAY_DOT_GRAY = "#9aa0a6"
TRAY_DOT_BLUE = "#7fb3ff"
"""有新版本（右下角）。"""

# 互動
SNAP_THRESHOLD = 12
SNAP_MARGIN = 8
HOVER_DELAY_MS = 500
HOUSEKEEPING_MS = 2_000
"""重設 TOPMOST、檢查全螢幕的間隔。"""
REPAINT_MS = 60_000
"""倒數文字重畫間隔（不打 API）。"""
OPACITY_CHOICES = (1.0, 0.9, 0.75, 0.6)
