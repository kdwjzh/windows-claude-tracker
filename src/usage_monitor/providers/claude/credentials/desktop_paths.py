"""Claude 桌面版資料夾的候選位置（CLAUDE.md §3.1）。

**桌面版路徑規則只能寫在這裡**：資料夾再搬家時只改這個檔案。
"""

from __future__ import annotations

import re
from pathlib import Path

from usage_monitor.platform import paths

PREFERRED_PUBLISHER = "pzs8sxrjxfjjc"

NEW_DIR = re.compile(r"^claude_[a-z0-9]{13}$")
"""%LOCALAPPDATA%\\Claude-Data\\ 底下，小寫 claude_（Store 版搬家後的新位置）。"""

PACKAGE_DIR = re.compile(r"^Claude_[a-z0-9]{13}$")
"""%LOCALAPPDATA%\\Packages\\ 底下，大寫 Claude_（舊的 Store 版）。"""

MOVED_MARKER_GLOB = ".user-data-left.*"
"""舊資料夾只剩這個標記檔時，代表資料已經搬家。"""


def _scan(parent: Path, pattern: re.Pattern[str]) -> list[Path]:
    try:
        found = [p for p in parent.iterdir() if pattern.match(p.name) and p.is_dir()]
    except OSError:
        return []
    return sorted(found, key=lambda p: (not p.name.endswith(PREFERRED_PUBLISHER), p.name))


def data_dirs(local: Path | None = None, roaming: Path | None = None) -> list[Path]:
    """依優先順序列出候選資料夾：新路徑 → 舊路徑（一般安裝）→ 舊路徑（Store）。

    舊路徑（一般安裝）即使不存在也列出，方便診斷。
    """
    local = local or paths.local()
    roaming = roaming or paths.roaming()
    dirs = _scan(local / "Claude-Data", NEW_DIR)
    dirs.append(roaming / "Claude")
    dirs += [
        p / "LocalCache" / "Roaming" / "Claude" for p in _scan(local / "Packages", PACKAGE_DIR)
    ]
    return dirs
