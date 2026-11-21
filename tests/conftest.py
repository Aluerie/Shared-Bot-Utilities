# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Shared pytest fixtures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

import orjson
import pytest
from yarl import URL

if TYPE_CHECKING:
    from collections.abc import Callable


class FakeResponse:
    """Just enough of ``aiohttp.ClientResponse`` for the API clients in ``shared.apis``."""

    def __init__(self, url: str, *, status: int = 200, json: Any = None, text: str | None = None) -> None:
        self.url: URL = URL(url)
        self.status: int = status
        self.ok: bool = 200 <= status < 300
        self._text: str = text if text is not None else orjson.dumps(json).decode()

    async def json(self, *, loads: Callable[[str], Any] = orjson.loads, **_: Any) -> Any:
        return loads(self._text)

    async def text(self) -> str:
        return self._text

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        pass


class FakeSession:
    """Fake ``aiohttp.ClientSession`` that answers requests with queued responses and records the calls.

    Queue responses with ``add(...)``; once only one is left, it keeps being reused,
    which is handy for testing retry loops.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self._responses: list[dict[str, Any]] = []
        self.closed: bool = False

    def add(self, *, status: int = 200, json: Any = None, text: str | None = None) -> Self:
        self._responses.append({"status": status, "json": json, "text": text})
        return self

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        if not self._responses:
            msg = f"FakeSession got an unexpected {method} {url}"
            raise AssertionError(msg)
        response = self._responses[0] if len(self._responses) == 1 else self._responses.pop(0)
        return FakeResponse(url, **response)

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        return self.request("POST", url, **kwargs)


@pytest.fixture
def session() -> FakeSession:
    """Return a fresh fake HTTP session."""
    return FakeSession()
