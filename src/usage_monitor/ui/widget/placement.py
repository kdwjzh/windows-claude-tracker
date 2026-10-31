"""小工具的位置計算：預設位置、邊緣貼齊、存檔與還原（純函式，不依賴 Qt）。

位置以「螢幕名稱＋相對該螢幕工作區左上角的座標」存檔，換解析度或拔掉螢幕時才能正確還原。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from usage_monitor.ui import theme


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def contains_point(self, px: int, py: int) -> bool:
        return self.x <= px < self.right and self.y <= py < self.bottom

    def contains(self, other: Rect, tolerance: int = 0) -> bool:
        return (
            other.x >= self.x - tolerance
            and other.y >= self.y - tolerance
            and other.right <= self.right + tolerance
            and other.bottom <= self.bottom + tolerance
        )


@dataclass(frozen=True)
class ScreenInfo:
    name: str
    work: Rect
    """工作區（已扣除工作列）。"""
    primary: bool = False


Size = tuple[int, int]
Point = tuple[int, int]


def primary_screen(screens: Sequence[ScreenInfo]) -> ScreenInfo:
    return next((s for s in screens if s.primary), screens[0])


def default_position(work: Rect, size: Size, margin: int = theme.SNAP_MARGIN) -> Point:
    """工作區右下角，距邊緣 8px（即工作列正上方、右側）。"""
    w, h = size
    return work.right - w - margin, work.bottom - h - margin


def snap(
    pos: Point,
    size: Size,
    work: Rect,
    threshold: int = theme.SNAP_THRESHOLD,
    margin: int = theme.SNAP_MARGIN,
) -> Point:
    """放開時距工作區邊緣 12px 內（含超出邊緣）就貼齊，貼齊後距邊緣 8px。"""
    x, y = pos
    w, h = size
    if x - work.x <= threshold:
        x = work.x + margin
    elif work.right - (x + w) <= threshold:
        x = work.right - w - margin
    if y - work.y <= threshold:
        y = work.y + margin
    elif work.bottom - (y + h) <= threshold:
        y = work.bottom - h - margin
    return x, y


def keep_anchor(pos: Point, old_width: int, new_width: int, work: Rect) -> Point:
    """寬度跟著文字改變時：小工具在螢幕右半邊就固定右緣（往左長），否則固定左緣。

    預設位置在右下角，這樣數字變長時小工具不會慢慢往螢幕外長出去。
    """
    x, y = pos
    if x + old_width / 2 > work.x + work.w / 2:
        x += old_width - new_width
    return x, y


def screen_for(pos: Point, size: Size, screens: Sequence[ScreenInfo]) -> ScreenInfo:
    """小工具中心點所在的螢幕；都不在時用主螢幕。"""
    cx, cy = pos[0] + size[0] // 2, pos[1] + size[1] // 2
    return next((s for s in screens if s.work.contains_point(cx, cy)), primary_screen(screens))


def to_saved(pos: Point, size: Size, screens: Sequence[ScreenInfo]) -> tuple[str, Point]:
    """全域座標 → (螢幕名稱, 相對該螢幕工作區的座標)。"""
    screen = screen_for(pos, size, screens)
    return screen.name, (pos[0] - screen.work.x, pos[1] - screen.work.y)


def restore(
    saved_screen: str | None,
    saved_pos: Point | None,
    size: Size,
    screens: Sequence[ScreenInfo],
) -> Point:
    """還原位置；螢幕不存在或位置超出可見範圍時，改放主螢幕預設位置。"""
    primary = primary_screen(screens)
    if saved_screen is None or saved_pos is None:
        return default_position(primary.work, size)
    screen = next((s for s in screens if s.name == saved_screen), None)
    if screen is None:
        return default_position(primary.work, size)
    x, y = screen.work.x + saved_pos[0], screen.work.y + saved_pos[1]
    if not screen.work.contains(Rect(x, y, *size), tolerance=theme.SNAP_THRESHOLD):
        return default_position(primary.work, size)
    return x, y
