from __future__ import annotations

import pytest

from fakes import FakeClock, FakeTransport
from usage_monitor.providers import registry


def test_claude_is_registered() -> None:
    assert "claude" in registry.available()
    provider = registry.create("claude", FakeTransport(), FakeClock())
    assert provider.id == "claude"


def test_unknown_provider() -> None:
    with pytest.raises(KeyError, match="nope"):
        registry.create("nope", FakeTransport(), FakeClock())
