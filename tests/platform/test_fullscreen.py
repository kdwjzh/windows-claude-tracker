"""前景視窗是否為全螢幕的判斷（純函式，不需要 Windows）。

2026-11-04 bug：最大化的瀏覽器讓影片進入全螢幕時，視窗仍是最大化狀態，
舊程式一看到 IsZoomed 就判定「不是全螢幕」，小工具因此沒有隱藏。
"""

from __future__ import annotations

import pytest

from usage_monitor.platform import fullscreen

MONITOR = (0, 0, 1920, 1080)
FULL = (0, 0, 1920, 1080)
NO_CAPTION = 0x16000000  # WS_POPUP | WS_VISIBLE | WS_CLIPSIBLINGS：瀏覽器影片全螢幕、遊戲
WITH_CAPTION = 0x16CF0000  # WS_OVERLAPPEDWINDOW | WS_VISIBLE | WS_MAXIMIZE 一類的一般視窗


@pytest.mark.parametrize(
    ("rect", "style", "class_name", "expected"),
    [
        # 最大化、沒有標題列、蓋滿螢幕：瀏覽器影片全螢幕（修之前會失敗）
        (FULL, NO_CAPTION | fullscreen.WS_MAXIMIZE, "Chrome_WidgetWin_1", True),
        # 最大化、有標題列：一般最大化視窗；工作列自動隱藏時矩形也會蓋滿螢幕
        (FULL, WITH_CAPTION | fullscreen.WS_MAXIMIZE, "Chrome_WidgetWin_1", False),
        ((-8, -8, 1928, 1088), WITH_CAPTION | fullscreen.WS_MAXIMIZE, "Notepad", False),
        # 非最大化、沒有標題列、蓋滿螢幕：遊戲或無邊框全螢幕
        (FULL, NO_CAPTION, "UnityWndClass", True),
        # 沒有蓋滿螢幕
        ((0, 0, 1920, 1040), NO_CAPTION, "Chrome_WidgetWin_1", False),
        ((100, 100, 900, 700), NO_CAPTION, "UnityWndClass", False),
        # 桌面與工作列本身
        (FULL, NO_CAPTION, "Progman", False),
        (FULL, NO_CAPTION, "WorkerW", False),
        (FULL, NO_CAPTION, "Shell_TrayWnd", False),
        (FULL, NO_CAPTION, "Shell_SecondaryTrayWnd", False),
    ],
)
def test_is_fullscreen_window(
    rect: tuple[int, int, int, int], style: int, class_name: str, expected: bool
) -> None:
    assert fullscreen.is_fullscreen_window(rect, MONITOR, style, class_name) is expected


def test_partial_caption_bits_are_not_a_caption() -> None:
    """WS_CAPTION 是 WS_BORDER＋WS_DLGFRAME 兩個位元；只有邊框（WS_BORDER）不算有標題列。"""
    assert fullscreen.is_fullscreen_window(FULL, MONITOR, NO_CAPTION | 0x00800000, "X") is True
