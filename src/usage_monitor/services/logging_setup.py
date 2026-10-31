"""log 設定＋token 遮罩（CLAUDE.md §5.1 第 1 條）。

遮罩做在 handler 上：不論訊息、參數、例外 traceback 裡出現 token，寫出前都會被遮掉。
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT_LOGGER = "usage_monitor"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 2
FORMAT = "%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s"

_TOKEN_RE = re.compile(
    r"(?P<sk>sk-ant-[a-z0-9]+-)[A-Za-z0-9_\-]+"
    r"|(?P<bearer>Bearer\s+)[^\s\"',;]+"
    r"|(?P<jwt>eyJ[\w-]*\.)[\w-]*\.?[\w-]*"
)


def mask_tokens(text: str) -> str:
    """`sk-ant-oat01-xxxx` → `sk-ant-oat01-***`；`Bearer xxx` → `Bearer ***`；JWT → `eyJ….***`。"""
    return _TOKEN_RE.sub(
        lambda m: (m.group("sk") or m.group("bearer") or m.group("jwt") or "") + "***", text
    )


class MaskTokensFilter(logging.Filter):
    """把訊息（含 % 參數）、例外 traceback、stack info 中的 token 遮掉。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_tokens(record.getMessage())
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = mask_tokens(record.exc_text)
        if record.stack_info:
            record.stack_info = mask_tokens(record.stack_info)
        return True


def setup_logging(log_file: Path | None, *, debug: bool = False) -> logging.Logger:
    """設定 `usage_monitor` logger。可重複呼叫：會先移除之前加上的 handler。

    `log_file` 為 None 時只輸出到 stderr（測試或主控台工具用）。
    """
    logger = logging.getLogger(ROOT_LOGGER)
    for h in list(logger.handlers):
        if getattr(h, "_usage_monitor", False):
            logger.removeHandler(h)
            h.close()

    handler: logging.Handler
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_file, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(FORMAT))
    handler.addFilter(MaskTokensFilter())
    handler._usage_monitor = True  # type: ignore[attr-defined]  # 標記成本模組加的

    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False
    return logger
