"""CodexProvider：auth.json → wham/usage → Usage。"""

from __future__ import annotations

import logging

from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.interfaces import Clock, Provider, Transport
from usage_monitor.core.models import Usage
from usage_monitor.providers.codex import api
from usage_monitor.providers.codex.credentials import CodexCredentialSource
from usage_monitor.providers.codex.parse import parse_usage

log = logging.getLogger(__name__)

PROVIDER_ID = "codex"
DISPLAY_NAME = "Codex"


class CodexProvider:
    id = PROVIDER_ID
    display_name = DISPLAY_NAME

    def __init__(self, source: CodexCredentialSource, transport: Transport, clock: Clock) -> None:
        self._source = source
        self._transport = transport
        self._clock = clock
        self._source_label: str | None = None

    def poll(self) -> Usage:
        auth = self._source.read_auth()
        if auth is None:
            self._source_label = None
            raise PollError(ErrKind.AUTH, "找不到 Codex 登入資訊", reason=ErrReason.NO_CREDENTIALS)
        self._source_label = auth.token.source
        if auth.token.is_expired(self._clock.now()):
            raise PollError(
                ErrKind.AUTH,
                "Codex 登入已過期，請執行 codex 讓它更新登入",
                reason=ErrReason.EXPIRED,
            )

        resp = api.get_usage(self._transport, auth.token.value, auth.account_id)
        try:
            body = resp.json()
        except ValueError as e:
            raise PollError(
                ErrKind.TRANSIENT, "Codex 用量 API 回應不是 JSON", reason=ErrReason.BAD_RESPONSE
            ) from e
        usage = parse_usage(body, self._clock.now())
        log.debug("Codex 週期：%s／%s", usage.session.label, usage.long.label)
        return usage

    def credential_signature(self) -> str:
        return self._source.signature()

    def source_label(self) -> str | None:
        return self._source_label


def create(transport: Transport, clock: Clock) -> Provider:
    return CodexProvider(CodexCredentialSource(), transport, clock)
