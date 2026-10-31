"""測試用的假物件：不碰網路、不等待真實時間。"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from usage_monitor.core.interfaces import Response, Token
from usage_monitor.core.models import Usage


class FakeClock:
    """固定時間，只在呼叫 advance() 時前進。"""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, tzinfo=UTC)
        if self._now.tzinfo is None:
            raise ValueError("FakeClock 只接受 UTC aware 時間")

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float = 0, **kwargs: float) -> datetime:
        self._now += timedelta(seconds=seconds, **kwargs)
        return self._now


@dataclass(frozen=True)
class Call:
    method: str
    url: str
    headers: Mapping[str, str]
    json: Any = None
    timeout: float = 0.0


class FakeTransport:
    """依 (method, url) 依序回傳預先排好的 Response 或丟出例外。"""

    def __init__(self) -> None:
        self._queues: dict[tuple[str, str], deque[Response | BaseException]] = {}
        self.calls: list[Call] = []

    def add(self, method: str, url: str, *results: Response | BaseException) -> FakeTransport:
        self._queues.setdefault((method.upper(), url), deque()).extend(results)
        return self

    def get(self, url: str, headers: Mapping[str, str], timeout: float) -> Response:
        self.calls.append(Call("GET", url, dict(headers), timeout=timeout))
        return self._next("GET", url)

    def post(self, url: str, headers: Mapping[str, str], json: Any, timeout: float) -> Response:
        self.calls.append(Call("POST", url, dict(headers), json=json, timeout=timeout))
        return self._next("POST", url)

    def _next(self, method: str, url: str) -> Response:
        queue = self._queues.get((method, url))
        if not queue:
            raise AssertionError(f"FakeTransport 沒有排好 {method} {url} 的回應")
        result = queue.popleft()
        if isinstance(result, BaseException):
            raise result
        return result


class FakeProvider:
    """依序回傳 Usage 或丟出例外；結果用完後重複最後一個。"""

    def __init__(
        self,
        provider_id: str = "fake",
        results: Iterable[Usage | BaseException] = (),
        *,
        display_name: str | None = None,
        signature: str = "sig-1",
        source: str | None = "假來源",
    ) -> None:
        self.id = provider_id
        self.display_name = display_name or provider_id.capitalize()
        self.results: deque[Usage | BaseException] = deque(results)
        self.signature = signature
        self.source = source
        self.poll_count = 0

    def poll(self) -> Usage:
        self.poll_count += 1
        if not self.results:
            raise AssertionError(f"FakeProvider {self.id} 沒有排好結果")
        result = self.results[0] if len(self.results) == 1 else self.results.popleft()
        if isinstance(result, BaseException):
            raise result
        return result

    def credential_signature(self) -> str:
        return self.signature

    def source_label(self) -> str | None:
        return self.source


class FakeCredentialSource:
    """回傳固定的 Token（或 None）；簽章可在測試中改變。"""

    def __init__(
        self, name: str = "假來源", token: Token | None = None, signature: str = "sig-1"
    ) -> None:
        self.name = name
        self.token = token
        self._signature = signature
        self.read_count = 0

    def read(self) -> Token | None:
        self.read_count += 1
        return self.token

    def signature(self) -> str:
        return self._signature

    def set_signature(self, value: str) -> None:
        self._signature = value
