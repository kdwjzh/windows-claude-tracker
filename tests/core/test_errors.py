from __future__ import annotations

from usage_monitor.core.errors import ErrKind, ErrReason, PollError


def test_poll_error_carries_kind_and_details() -> None:
    err = PollError(ErrKind.TRANSIENT, "HTTP 429", status=429, retry_after=60.0)
    assert err.kind is ErrKind.TRANSIENT
    assert err.status == 429
    assert err.retry_after == 60.0
    assert str(err) == "HTTP 429"


def test_poll_error_reason() -> None:
    err = PollError(ErrKind.AUTH, "x", reason=ErrReason.EXPIRED)
    assert err.reason is ErrReason.EXPIRED
    assert repr(err) == "PollError(AUTH, 'x', status=None, reason=EXPIRED)"


def test_poll_error_defaults() -> None:
    err = PollError(ErrKind.AUTH, "找不到 token")
    assert err.status is None
    assert err.retry_after is None
    assert repr(err) == "PollError(AUTH, '找不到 token', status=None)"
