from __future__ import annotations

import logging

import pytest

from usage_monitor.core.models import ProviderState
from usage_monitor.services.state_store import StateStore
from usage_monitor.services.subscribers import Subscribers


def state(pid: str, stale: bool = False) -> ProviderState:
    return ProviderState(pid, usage=None, error=None, stale=stale, source_label=None)


def test_update_get_all_remove() -> None:
    store = StateStore()
    a, b = state("claude"), state("codex")
    store.update(a)
    store.update(b)
    assert store.get("claude") is a
    assert store.all() == {"claude": a, "codex": b}
    store.remove("claude")
    store.remove("missing")
    assert store.get("claude") is None


def test_update_replaces_and_notifies() -> None:
    store = StateStore()
    seen: list[ProviderState] = []
    unsubscribe = store.subscribe(seen.append)
    first, second = state("claude"), state("claude", stale=True)
    store.update(first)
    store.update(second)
    assert store.get("claude") is second
    assert seen == [first, second]
    unsubscribe()
    unsubscribe()  # 重複取消不會出錯
    store.update(first)
    assert len(seen) == 2


def test_failing_subscriber_does_not_block_others(caplog: pytest.LogCaptureFixture) -> None:
    subs: Subscribers[int] = Subscribers()
    seen: list[int] = []

    def broken(_: int) -> None:
        raise RuntimeError("boom")

    subs.add(broken)
    subs.add(seen.append)
    with caplog.at_level(logging.ERROR):
        subs.notify(1)
    assert seen == [1]
    assert "訂閱者" in caplog.text
