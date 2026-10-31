"""Claude Code CLI 的明文憑證。

位置：%CLAUDE_CONFIG_DIR%\\.credentials.json，未設定則 ~/.claude/.credentials.json。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from usage_monitor.core.interfaces import Token
from usage_monitor.core.json_access import as_dict, as_str, parse_unix_ms
from usage_monitor.platform import paths

log = logging.getLogger(__name__)

SOURCE_NAME = "cli"


def credentials_path() -> Path:
    custom = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(custom) if custom else paths.home() / ".claude"
    return base / ".credentials.json"


class CliCredentialSource:
    name = SOURCE_NAME

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path or credentials_path()

    def read(self) -> Token | None:
        try:
            data: object = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            log.debug("CLI 憑證讀取失敗：%s", type(e).__name__)
            return None
        oauth = as_dict((as_dict(data) or {}).get("claudeAiOauth"))
        if oauth is None:
            return None
        token = (as_str(oauth.get("accessToken")) or "").strip()
        if not token:
            return None
        return Token(token, expires_at=parse_unix_ms(oauth.get("expiresAt")), source=self.name)

    def signature(self) -> str:
        """路徑＋大小＋mtime（CLI 檔只有登入時才會改）。"""
        p = self.path
        try:
            st = p.stat()
        except OSError:
            return f"{p}|missing"
        return f"{p}|{st.st_size}|{st.st_mtime_ns}"
