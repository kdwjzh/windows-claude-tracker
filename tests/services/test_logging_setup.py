from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from usage_monitor.services.logging_setup import (
    MaskTokensFilter,
    mask_tokens,
    setup_logging,
)

SK = "sk-ant-oat01-AbCdEf_123-xyz"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJl"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (f"token={SK} end", "token=sk-ant-oat01-*** end"),
        ("Authorization: Bearer abc.def-ghi", "Authorization: Bearer ***"),
        ("{'Authorization': 'Bearer secret123'}", "{'Authorization': 'Bearer ***'}"),
        (f"jwt {JWT} done", "jwt eyJhbGciOiJIUzI1NiJ9.*** done"),
        ("nothing secret here", "nothing secret here"),
    ],
)
def test_mask_tokens(text: str, expected: str) -> None:
    assert mask_tokens(text) == expected


def _record(msg: str, *args: object, exc: BaseException | None = None) -> logging.LogRecord:
    exc_info = (type(exc), exc, exc.__traceback__) if exc else None
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, args or None, exc_info)


def test_filter_masks_args() -> None:
    record = _record("headers=%s", {"Authorization": f"Bearer {SK}"})
    MaskTokensFilter().filter(record)
    assert SK not in record.getMessage()
    assert "Bearer ***" in record.getMessage()


def test_filter_masks_exception_text() -> None:
    try:
        raise ValueError(f"bad token {SK}")
    except ValueError as e:
        record = _record("failed", exc=e)
    MaskTokensFilter().filter(record)
    text = logging.Formatter().format(record)
    assert SK not in text
    assert "sk-ant-oat01-***" in text


def test_filter_masks_stack_info() -> None:
    record = _record("x")
    record.stack_info = f"Stack: {SK}"
    MaskTokensFilter().filter(record)
    assert record.stack_info == "Stack: sk-ant-oat01-***"


def _ours(logger: logging.Logger) -> list[logging.Handler]:
    return [h for h in logger.handlers if getattr(h, "_usage_monitor", False)]


@pytest.fixture
def clean_logger() -> Iterator[None]:
    yield
    logger = logging.getLogger("usage_monitor")
    for h in _ours(logger):  # 關掉檔案 handler，避免 Windows 鎖住暫存檔
        logger.removeHandler(h)
        h.close()
    logger.propagate = True  # 讓其他測試的 caplog 收得到
    logger.setLevel(logging.NOTSET)


@pytest.mark.usefixtures("clean_logger")
def test_setup_writes_masked_file(tmp_path: Path) -> None:
    log_file = tmp_path / "sub" / "monitor.log"
    setup_logging(log_file)
    child = logging.getLogger("usage_monitor.providers.claude")
    child.info("using %s", f"Bearer {SK}")
    child.debug("hidden at INFO level")
    for h in logging.getLogger("usage_monitor").handlers:
        h.flush()
    content = log_file.read_text(encoding="utf-8")
    assert "using Bearer ***" in content
    assert SK not in content
    assert "hidden" not in content


@pytest.mark.usefixtures("clean_logger")
def test_setup_is_idempotent_and_debug(tmp_path: Path) -> None:
    setup_logging(tmp_path / "a.log")
    logger = setup_logging(tmp_path / "b.log", debug=True)
    assert len(_ours(logger)) == 1
    assert logger.level == logging.DEBUG
    assert logger.propagate is False
