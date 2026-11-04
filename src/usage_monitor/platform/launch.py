"""用預設程式開啟檔案、資料夾與網址。"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def open_path(path: Path) -> None:
    """用預設程式開啟檔案或資料夾（例如 log）。"""
    if sys.platform != "win32":
        return
    try:
        os.startfile(path)
    except OSError as e:
        log.warning("無法開啟 %s：%s", path, type(e).__name__)


def open_url(url: str) -> None:
    """用預設瀏覽器開啟網址；只接受 https。"""
    if not url.startswith("https://"):
        log.warning("拒絕開啟非 https 網址")
        return
    if sys.platform != "win32":
        return
    try:
        os.startfile(url)
    except OSError as e:
        log.warning("無法開啟網址：%s", type(e).__name__)
