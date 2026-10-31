from __future__ import annotations

import pytest

from usage_monitor.ui.widget.placement import (
    Rect,
    ScreenInfo,
    default_position,
    keep_anchor,
    restore,
    screen_for,
    snap,
    to_saved,
)

SIZE = (500, 70)
PRIMARY = ScreenInfo(r"\\.\DISPLAY1", Rect(0, 0, 1920, 1040), primary=True)  # 工作列 40px
SECOND = ScreenInfo(r"\\.\DISPLAY2", Rect(1920, -200, 2560, 1400))
SCREENS = [SECOND, PRIMARY]


def test_default_position_is_above_taskbar_on_the_right() -> None:
    assert default_position(PRIMARY.work, SIZE) == (1920 - 500 - 8, 1040 - 70 - 8)


@pytest.mark.parametrize(
    ("pos", "expected"),
    [
        ((100, 100), (100, 100)),  # 離邊緣很遠：不動
        ((12, 100), (8, 100)),  # 左邊 12px 內 → 貼齊
        ((13, 100), (13, 100)),  # 13px：不貼
        ((-30, 100), (8, 100)),  # 超出左邊也拉回
        ((1920 - 500 - 5, 100), (1920 - 500 - 8, 100)),  # 右邊
        ((100, 3), (100, 8)),  # 上邊
        ((100, 1040 - 70 - 12), (100, 1040 - 70 - 8)),  # 下邊（工作列上方）
        ((1920 - 500, 1040 - 70), (1412, 962)),  # 右下角：兩個方向都貼齊
    ],
)
def test_snap(pos: tuple[int, int], expected: tuple[int, int]) -> None:
    assert snap(pos, SIZE, PRIMARY.work) == expected


def test_snap_on_secondary_screen_with_offset_origin() -> None:
    assert snap((1925, -195), SIZE, SECOND.work) == (1928, -192)


@pytest.mark.parametrize(
    ("pos", "expected"),
    [
        ((1412, 962), (1382, 962)),  # 右半邊：寬度 +30 → 往左長，右緣不動
        ((100, 962), (100, 962)),  # 左半邊：左緣不動
    ],
)
def test_keep_anchor_when_width_grows(pos: tuple[int, int], expected: tuple[int, int]) -> None:
    assert keep_anchor(pos, 500, 530, PRIMARY.work) == expected


def test_keep_anchor_when_width_shrinks_on_right() -> None:
    assert keep_anchor((1412, 962), 500, 470, PRIMARY.work) == (1442, 962)


def test_screen_for_uses_center_and_falls_back_to_primary() -> None:
    assert screen_for((2000, 0), SIZE, SCREENS) is SECOND
    assert screen_for((100, 100), SIZE, SCREENS) is PRIMARY
    assert screen_for((-5000, -5000), SIZE, SCREENS) is PRIMARY


def test_save_and_restore_round_trip_on_second_screen() -> None:
    name, rel = to_saved((2500, 300), SIZE, SCREENS)
    assert (name, rel) == (r"\\.\DISPLAY2", (580, 500))
    assert restore(name, rel, SIZE, SCREENS) == (2500, 300)


def test_restore_without_saved_position_uses_default() -> None:
    assert restore(None, None, SIZE, SCREENS) == default_position(PRIMARY.work, SIZE)


def test_restore_missing_screen_falls_back_to_primary_default() -> None:
    """拔掉第二個螢幕後回到主螢幕。"""
    assert restore(r"\\.\DISPLAY2", (580, 500), SIZE, [PRIMARY]) == default_position(
        PRIMARY.work, SIZE
    )


def test_restore_out_of_visible_range_falls_back() -> None:
    """換成較小的解析度後，原本的位置已經在畫面外。"""
    small = ScreenInfo(r"\\.\DISPLAY1", Rect(0, 0, 1280, 680), primary=True)
    assert restore(r"\\.\DISPLAY1", (1400, 900), SIZE, [small]) == default_position(
        small.work, SIZE
    )


def test_restore_allows_slight_overhang() -> None:
    assert restore(r"\\.\DISPLAY1", (-10, 0), SIZE, [PRIMARY]) == (-10, 0)


def test_primary_falls_back_to_first_screen() -> None:
    only = ScreenInfo("A", Rect(0, 0, 800, 600))
    assert restore(None, None, (100, 50), [only]) == (692, 542)


def test_rect_helpers() -> None:
    r = Rect(10, 20, 30, 40)
    assert (r.right, r.bottom) == (40, 60)
    assert r.contains_point(10, 20) and not r.contains_point(40, 20)
    assert r.contains(Rect(10, 20, 30, 40))
    assert not r.contains(Rect(9, 20, 30, 40))
    assert r.contains(Rect(9, 20, 30, 40), tolerance=1)
