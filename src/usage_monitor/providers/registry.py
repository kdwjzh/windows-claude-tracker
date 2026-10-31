"""已註冊的服務。新增服務：新增 providers/<name>/，並在這裡加一行。"""

from __future__ import annotations

from collections.abc import Callable

from usage_monitor.core.interfaces import Clock, Provider, Transport
from usage_monitor.providers.claude import provider as claude
from usage_monitor.providers.codex import provider as codex

ProviderFactory = Callable[[Transport, Clock], Provider]

FACTORIES: dict[str, ProviderFactory] = {
    claude.PROVIDER_ID: claude.create,
    codex.PROVIDER_ID: codex.create,
}


def available() -> list[str]:
    return list(FACTORIES)


def create(provider_id: str, transport: Transport, clock: Clock) -> Provider:
    try:
        factory = FACTORIES[provider_id]
    except KeyError:
        raise KeyError(f"未知的服務：{provider_id}") from None
    return factory(transport, clock)
