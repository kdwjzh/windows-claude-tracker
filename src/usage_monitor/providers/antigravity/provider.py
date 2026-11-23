"""AntigravityProvider：hub_*.json → 本機 RetrieveUserQuotaSummary → Usage。

方案另外問本機的 GetUserStatus（只讀 userTier.id）。
"""

from __future__ import annotations

import dataclasses
import logging

from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.interfaces import Clock, Provider, Response, Transport
from usage_monitor.core.models import Usage
from usage_monitor.providers.antigravity import api
from usage_monitor.providers.antigravity.hub import Hub, HubSource
from usage_monitor.providers.antigravity.parse import parse_plan, parse_usage

log = logging.getLogger(__name__)

PROVIDER_ID = "antigravity"
DISPLAY_NAME = "Antigravity"


def _json(resp: Response) -> object:
    try:
        return resp.json()
    except ValueError as e:
        raise PollError(
            ErrKind.TRANSIENT, "Antigravity 回應不是 JSON", reason=ErrReason.BAD_RESPONSE
        ) from e


class AntigravityProvider:
    id = PROVIDER_ID
    display_name = DISPLAY_NAME

    def __init__(self, source: HubSource, transport: Transport, clock: Clock) -> None:
        self._source = source
        self._transport = transport
        self._clock = clock
        self._source_label: str | None = None

    def poll(self) -> Usage:
        hub = self._source.read()
        if hub is None:
            self._source_label = None
            # 暫停輪詢，等 hub 檔改變（Antigravity 開啟）再試；不是需要使用者處理的錯誤
            raise PollError(ErrKind.AUTH, "Antigravity 沒有在執行", reason=ErrReason.NOT_RUNNING)
        self._source_label = self._source.name
        usage = parse_usage(_json(api.call(self._transport, hub, "RetrieveUserQuotaSummary")),
                            self._clock.now())  # fmt: skip
        return dataclasses.replace(usage, plan=self._plan(hub))

    def _plan(self, hub: Hub) -> str | None:
        """方案查不到只是不顯示標籤，不讓輪詢失敗。"""
        try:
            return parse_plan(_json(api.call(self._transport, hub, "GetUserStatus")))
        except PollError as e:
            log.debug("Antigravity 方案查詢失敗：%r", e)
            return None

    def credential_signature(self) -> str:
        return self._source.signature()

    def source_label(self) -> str | None:
        return self._source_label


def create(transport: Transport, clock: Clock) -> Provider:
    return AntigravityProvider(HubSource(), transport, clock)
