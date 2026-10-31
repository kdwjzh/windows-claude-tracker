from __future__ import annotations

import pytest

from usage_monitor.core import app_info
from usage_monitor.core.semver import Version, is_newer_release, parse


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.2.3", Version(1, 2, 3)),
        ("v1.2.3", Version(1, 2, 3)),
        (" v0.9.0 ", Version(0, 9, 0)),
        ("1.2.3-beta.1", Version(1, 2, 3, "beta.1")),
        ("1.2.3+build.5", Version(1, 2, 3)),
        ("1.2", None),
        ("1.2.3.4", None),
        ("latest", None),
        ("", None),
        (None, None),
    ],
)
def test_parse(text: str | None, expected: Version | None) -> None:
    assert parse(text) == expected


@pytest.mark.parametrize(
    ("candidate", "current", "newer"),
    [
        ("1.10.0", "1.9.0", True),  # 數字比較，不是字串比較
        ("v1.0.1", "1.0.0", True),
        ("2.0.0", "1.99.99", True),
        ("1.0.0", "1.0.0", False),
        ("0.9.0", "1.0.0", False),
        ("1.1.0-beta.1", "1.0.0", False),  # pre-release 不算新版
        ("1.2.0", "1.2.0-beta.1", True),  # 正式版比同號 beta 新
        ("1.2.0", "1.2.0-rc.2", True),
        ("garbage", "1.0.0", False),  # 格式錯誤不丟例外
        ("1.0.0", "garbage", False),
        (None, "1.0.0", False),
    ],
)
def test_is_newer_release(candidate: str | None, current: str | None, newer: bool) -> None:
    assert is_newer_release(candidate, current) is newer


def test_version_str_and_order() -> None:
    assert str(Version(1, 2, 3, "rc.1")) == "1.2.3-rc.1"
    assert str(Version(1, 2, 3)) == "1.2.3"
    assert Version(1, 10, 0) > Version(1, 9, 9)


def test_app_info_urls_point_at_repo() -> None:
    assert app_info.RELEASES_URL == "https://github.com/kdwjzh/windows-claude-tracker/releases"
    assert app_info.LATEST_RELEASE_API == (
        "https://api.github.com/repos/kdwjzh/windows-claude-tracker/releases/latest"
    )
