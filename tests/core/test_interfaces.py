from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from usage_monitor.core.interfaces import Response, Token

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def test_token_value_not_in_repr() -> None:
    token = Token("sk-ant-oat01-SECRET", expires_at=None, source="CLI")
    assert "SECRET" not in repr(token)
    assert "CLI" in repr(token)


@pytest.mark.parametrize(
    ("expires_at", "expired"),
    [
        (None, False),
        (NOW + timedelta(seconds=1), False),
        (NOW, True),
        (NOW - timedelta(hours=1), True),
    ],
)
def test_token_is_expired(expires_at: datetime | None, expired: bool) -> None:
    assert Token("t", expires_at=expires_at, source="CLI").is_expired(NOW) is expired


def test_response_header_is_case_insensitive() -> None:
    resp = Response(200, {"Retry-After": "30"})
    assert resp.header("retry-after") == "30"
    assert resp.header("RETRY-AFTER") == "30"
    assert resp.header("missing") is None


def test_response_json() -> None:
    assert Response(200, body=b'{"a": 1}').json() == {"a": 1}


def test_response_json_invalid_raises_value_error() -> None:
    with pytest.raises(ValueError):
        Response(200, body=b"<html>").json()
