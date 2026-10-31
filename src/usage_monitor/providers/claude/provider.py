"""ClaudeProvider：依序嘗試 token 來源 → 用量 API → （必要時）Messages 備援 → Usage。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from usage_monitor.core.errors import ErrKind, ErrReason, PollError
from usage_monitor.core.interfaces import Clock, CredentialSource, Provider, Token, Transport
from usage_monitor.core.models import Usage
from usage_monitor.providers.claude import api
from usage_monitor.providers.claude.credentials.cli import SOURCE_NAME as CLI_SOURCE
from usage_monitor.providers.claude.credentials.cli import CliCredentialSource
from usage_monitor.providers.claude.credentials.desktop import DesktopCredentialSource
from usage_monitor.providers.claude.parse import parse_headers, parse_usage

log = logging.getLogger(__name__)

PROVIDER_ID = "claude"
DISPLAY_NAME = "Claude"


class ClaudeProvider:
    id = PROVIDER_ID
    display_name = DISPLAY_NAME

    def __init__(
        self, sources: Sequence[CredentialSource], transport: Transport, clock: Clock
    ) -> None:
        self._sources = list(sources)
        self._transport = transport
        self._clock = clock
        self._source_label: str | None = None
        self._cli_refresher: Callable[[], bool] | None = None
        self._cli_refresh_enabled: Callable[[], bool] = lambda: False

    def configure_cli_refresh(
        self, refresher: Callable[[], bool], enabled: Callable[[], bool]
    ) -> None:
        """階段 7：沒有其他可用 token、且 CLI token 過期時，呼叫 refresher 讓 CLI 自己更新。

        `enabled` 每次都重新讀（對應設定 allow_cli_refresh，可隨時切換）。
        """
        self._cli_refresher = refresher
        self._cli_refresh_enabled = enabled

    def _read(self, source: CredentialSource) -> Token | None:
        try:
            return source.read()
        except Exception:  # 來源不應該丟例外；萬一有，也只略過這個來源
            log.exception("token 來源 %s 發生未預期錯誤", source.name)
            return None

    def _try_cli_refresh(self, source: CredentialSource) -> Token | None:
        if source.name != CLI_SOURCE or self._cli_refresher is None:
            return None
        if not self._cli_refresh_enabled():
            return None
        try:
            refreshed = self._cli_refresher()
        except Exception:
            log.exception("CLI token 更新時發生未預期錯誤")
            return None
        if not refreshed:
            return None
        token = self._read(source)
        if token is not None and not token.is_expired(self._clock.now()):
            return token
        log.warning("claude 執行完成，但 CLI token 仍然過期或讀不到")
        return None

    def _token(self) -> Token:
        """依序找第一個未過期的 token；CLI 過期時會往下找桌面版。

        都找不到可用的、而 CLI token 只是過期時，若設定允許，讓 CLI 自己更新後再讀一次。
        """
        now = self._clock.now()
        expired: Token | None = None
        expired_sources: list[CredentialSource] = []
        for source in self._sources:
            token = self._read(source)
            if token is None:
                continue
            if not token.is_expired(now):
                return token
            expired = expired or token
            expired_sources.append(source)
        for source in expired_sources:
            refreshed = self._try_cli_refresh(source)
            if refreshed is not None:
                return refreshed
        if expired is not None:
            self._source_label = expired.source
            raise PollError(
                ErrKind.AUTH,
                f"Claude 登入已過期（來源：{expired.source}）",
                reason=ErrReason.EXPIRED,
            )
        self._source_label = None
        raise PollError(ErrKind.AUTH, "找不到 Claude 登入資訊", reason=ErrReason.NO_CREDENTIALS)

    def poll(self) -> Usage:
        token = self._token()
        self._source_label = token.source
        log.debug("使用 token 來源：%s", token.source)
        try:
            resp = api.get_usage(self._transport, token.value)
        except PollError as e:
            if e.kind is not ErrKind.UNSUPPORTED:
                raise
            log.info("用量 API 不支援（HTTP %s），改用 Messages 備援", e.status)
            resp = api.probe_messages(self._transport, token.value)
            return parse_headers(resp.header, self._clock.now())
        try:
            body = resp.json()
        except ValueError as e:
            raise PollError(
                ErrKind.TRANSIENT, "用量 API 回應不是 JSON", reason=ErrReason.BAD_RESPONSE
            ) from e
        return parse_usage(body, self._clock.now())

    def credential_signature(self) -> str:
        return ";".join(s.signature() for s in self._sources)

    def source_label(self) -> str | None:
        return self._source_label


def create(transport: Transport, clock: Clock) -> Provider:
    """預設的 token 來源順序：CLI（未過期才用）→ 桌面版各候選路徑。"""
    return ClaudeProvider([CliCredentialSource(), DesktopCredentialSource(clock)], transport, clock)
