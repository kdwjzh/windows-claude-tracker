from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from usage_monitor.core.errors import ErrKind, PollError
from usage_monitor.core.models import ProviderState, Usage, Window

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def test_window_defaults_mean_no_data() -> None:
    w = Window()
    assert w.available is False
    assert w.percent == 0.0
    assert w.resets_at is None
    assert w.label is None


def test_zero_percent_is_still_available() -> None:
    assert Window(available=True, percent=0.0).available is True


@pytest.mark.parametrize(
    "obj",
    [
        Window(),
        Usage(session=Window(), long=Window(), fetched_at=NOW),
        ProviderState("claude", usage=None, error=None, stale=False, source_label=None),
    ],
)
def test_models_are_frozen(obj: object) -> None:
    field = dataclasses.fields(obj)[0].name  # type: ignore[arg-type]
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(obj, field, None)


def test_provider_state_keeps_last_usage_with_error() -> None:
    usage = Usage(Window(True, 42, label="5h"), Window(True, 18, label="7d"), NOW)
    err = PollError(ErrKind.TRANSIENT, "逾時")
    state = ProviderState("claude", usage=usage, error=err, stale=True, source_label="桌面版")
    assert state.usage is usage
    assert state.error is err
    assert state.stale
