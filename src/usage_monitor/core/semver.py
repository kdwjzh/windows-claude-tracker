"""版本號解析與比較（SemVer 的子集，純函式）。格式錯誤一律回傳 None／False，不丟例外。"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: str | None = None

    @property
    def is_prerelease(self) -> bool:
        return self.prerelease is not None

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.prerelease}" if self.prerelease else base


def parse(text: str | None) -> Version | None:
    """ "v1.2.0"、"1.2.0"、"1.2.0-beta.1"（可帶 +build）→ Version；其他回傳 None。"""
    if not text:
        return None
    m = _PATTERN.match(text.strip())
    if not m:
        return None
    return Version(int(m[1]), int(m[2]), int(m[3]), m[4])


def is_newer_release(candidate: str | None, current: str | None) -> bool:
    """candidate 是不是比 current 新的「正式版」：pre-release 不算新版；任一方格式錯誤就是 False。

    current 本身是 pre-release 時，同號的正式版算新版（1.2.0 > 1.2.0-beta.1）。
    """
    new, cur = parse(candidate), parse(current)
    if new is None or cur is None or new.is_prerelease:
        return False
    if (new.major, new.minor, new.patch) != (cur.major, cur.minor, cur.patch):
        return (new.major, new.minor, new.patch) > (cur.major, cur.minor, cur.patch)
    return cur.is_prerelease
