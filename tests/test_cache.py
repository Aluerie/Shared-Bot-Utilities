# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Tests for ``shared.cache``."""

import asyncio
import contextlib
from typing import TYPE_CHECKING

import pytest
from loguru import logger

from shared import cache

if TYPE_CHECKING:
    from loguru import Message


class Clock:
    """Controllable replacement for ``time.monotonic``."""

    def __init__(self) -> None:
        self.now: float = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(cache.time, "monotonic", fake)
    return fake


def test_expiring_cache(clock: Clock) -> None:
    expiring = cache.ExpiringCache(seconds=10)
    expiring["a"] = 1
    assert "a" in expiring
    assert expiring["a"] == 1
    assert expiring.get("a") == 1
    assert list(expiring.items()) == [("a", 1)]

    clock.now += 11
    assert "a" not in expiring
    assert expiring.get("a", "gone") == "gone"
    assert len(expiring) == 0
    with pytest.raises(KeyError):
        expiring["a"]


def test_expiring_cache_keeps_entries_until_ttl_passes(clock: Clock) -> None:
    expiring = cache.ExpiringCache(seconds=10)
    expiring["a"] = 1
    clock.now += 9
    assert expiring["a"] == 1
    clock.now += 2
    assert "a" not in expiring


def test_expiring_cache_views_skip_expired_entries(clock: Clock) -> None:
    expiring = cache.ExpiringCache(seconds=10)
    expiring["old"] = 1
    clock.now += 6
    expiring["new"] = 2
    clock.now += 6  # "old" is 12 seconds old, "new" is 6
    assert len(expiring) == 1
    assert list(expiring) == ["new"]
    assert list(expiring.values()) == [2]
    assert list(expiring.items()) == [("new", 2)]


@pytest.mark.parametrize("strategy", list(cache.Strategy))
async def test_cache_reuses_results(strategy: cache.Strategy) -> None:
    calls: list[int] = []

    @cache.cache(maxsize=60, strategy=strategy)
    async def double(x: int) -> int:
        calls.append(x)
        return x * 2

    assert await double(2) == 4
    assert await double(2) == 4
    assert await double(3) == 6
    assert calls == [2, 3]

    assert double.invalidate(2) is True
    assert double.invalidate(2) is False
    assert await double(2) == 4
    assert calls == [2, 3, 2]


async def test_concurrent_calls_share_one_task() -> None:
    calls = 0

    @cache.cache()
    async def slow() -> int:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return 42

    assert await asyncio.gather(slow(), slow(), slow()) == [42, 42, 42]
    assert calls == 1


async def test_failed_calls_are_not_cached() -> None:
    attempts = 0

    @cache.cache()
    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            msg = "first call fails"
            raise RuntimeError(msg)
        return "ok"

    with pytest.raises(RuntimeError):
        await flaky()
    await asyncio.sleep(0)  # let the done-callback evict the failed task
    assert await flaky() == "ok"


async def test_cache_key_ignores_kwarg_order_and_connection() -> None:
    @cache.cache()
    async def func(*, a: int, b: int, connection: object = None) -> int:
        return a + b

    assert func.get_key(a=1, b=2, connection=object()) == func.get_key(b=2, a=1)


async def test_invalidate_containing() -> None:
    @cache.cache()
    async def get_user(user_id: int) -> int:
        return user_id

    await get_user(1)
    await get_user(2)
    get_user.invalidate_containing("get_user:1")
    assert len(get_user.cache) == 1


async def test_ignore_kwargs() -> None:
    @cache.cache(ignore_kwargs=True)
    async def add(a: int, *, extra: int = 0) -> int:
        return a + extra

    first = add(1, extra=1)
    assert add(1, extra=2) is first
    assert await first == 2


async def test_cancelled_calls_are_not_cached() -> None:
    @cache.cache()
    async def slow() -> str:
        await asyncio.sleep(10)
        return "late"

    first = slow()
    await asyncio.sleep(0)
    first.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await first
    await asyncio.sleep(0)  # let the done-callback evict the cancelled task

    second = slow()
    assert second is not first
    second.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await second


async def test_failure_is_logged_even_if_nobody_awaits() -> None:
    messages: list[Message] = []

    @cache.cache()
    async def broken() -> None:
        msg = "nobody sees me"
        raise RuntimeError(msg)

    handler_id = logger.add(messages.append, level="WARNING")
    try:
        broken()  # fire and forget
        await asyncio.sleep(0.01)
    finally:
        logger.remove(handler_id)

    assert len(messages) == 1
    exception = messages[0].record["exception"]
    assert exception is not None
    assert isinstance(exception.value, RuntimeError)


async def test_lru_forgets_the_least_recently_used() -> None:
    calls: list[int] = []

    @cache.cache(maxsize=1)
    async def value(x: int) -> int:
        calls.append(x)
        return x

    await value(1)
    await value(2)
    await value(1)
    assert calls == [1, 2, 1]


async def test_timed_strategy_expires_results(clock: Clock) -> None:
    calls = 0

    @cache.cache(maxsize=10, strategy=cache.Strategy.timed)  # `maxsize` is the TTL in seconds for this strategy
    async def value() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert await value() == 1
    clock.now += 5
    assert await value() == 1
    clock.now += 6
    assert await value() == 2
