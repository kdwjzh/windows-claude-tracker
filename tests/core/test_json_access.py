from __future__ import annotations

from datetime import UTC, datetime

import pytest

from usage_monitor.core import json_access as j


def test_as_dict_list_str() -> None:
    assert j.as_dict({"a": 1}) == {"a": 1}
    assert j.as_dict([1]) is None
    assert j.as_list([1]) == [1]
    assert j.as_list({}) is None
    assert j.as_str("x") == "x"
    assert j.as_str(1) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (42, 42.0),
        (18.5, 18.5),
        ("0.25", 0.25),
        ("abc", None),
        (True, None),
        (None, None),
        ([], None),
    ],
)
def test_as_float(value: object, expected: float | None) -> None:
    assert j.as_float(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-10-29T12:00:00Z", datetime(2026, 10, 29, 12, tzinfo=UTC)),
        ("2026-10-29T20:00:00+08:00", datetime(2026, 10, 29, 12, tzinfo=UTC)),
        ("2026-10-29T12:00:00", datetime(2026, 10, 29, 12, tzinfo=UTC)),
        ("not a date", None),
        ("", None),
        (None, None),
        (12345, None),
    ],
)
def test_parse_iso(value: object, expected: datetime | None) -> None:
    result = j.parse_iso(value)
    assert result == expected
    if result is not None:
        assert result.tzinfo is UTC


def test_parse_unix_and_ms() -> None:
    expected = datetime(2026, 10, 29, 12, tzinfo=UTC)
    ts = expected.timestamp()
    assert j.parse_unix(int(ts)) == expected
    assert j.parse_unix(str(int(ts))) == expected
    assert j.parse_unix_ms(ts * 1000) == expected
    assert j.parse_unix(0) is None
    assert j.parse_unix("x") is None
    assert j.parse_unix(1e30) is None
    assert j.parse_unix_ms(None) is None
