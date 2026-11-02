# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Cache.

References
----------
* RoboDanny (MPL v2 License):
  https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/utils/cache.py
"""

import asyncio
import contextlib
import enum
import logging
import operator
import time
from functools import wraps
from typing import TYPE_CHECKING, Any, Protocol, assert_never, override

from lru import LRU

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Iterator, MutableMapping


__all__ = (
    "ExpiringCache",
    "Strategy",
    "cache",
)

log = logging.getLogger(__name__)


# Can't use ParamSpec due to https://github.com/python/typing/discussions/946
class CacheProtocol[R](Protocol):
    cache: MutableMapping[str, asyncio.Task[R]]

    def __call__(self, *args: Any, **kwargs: Any) -> asyncio.Task[R]: ...

    def get_key(self, *args: Any, **kwargs: Any) -> str: ...

    def invalidate(self, *args: Any, **kwargs: Any) -> bool: ...

    def invalidate_containing(self, key: str) -> None: ...

    def get_stats(self) -> tuple[int, int]: ...


class ExpiringCache(dict[Any, Any]):  # ruff: ignore[subclass-builtin]
    """A dictionary whose entries expire a while after they were set.

    Parameters
    ----------
    seconds
        Time to live of an entry.

    Notes
    -----
    Only ``[]``, ``in``, ``get``, ``values``, ``items``, ``len`` and iteration are aware of the expiration.
    Other ``dict`` methods (``update``, ``setdefault``, ``pop``, ``copy``, ...) bypass the timestamps,
    so don't use them.
    """

    def __init__(self, seconds: float) -> None:
        self.__ttl: float = seconds
        super().__init__()

    def __verify_cache_integrity(self) -> None:
        # Have to do this in two steps...
        current_time = time.monotonic()
        to_remove = [k for (k, (_, t)) in super().items() if current_time > (t + self.__ttl)]
        for k in to_remove:
            del self[k]

    @override
    def __contains__(self, key: str) -> bool:  # ty: ignore[invalid-method-override]
        self.__verify_cache_integrity()
        return super().__contains__(key)

    @override
    def __getitem__(self, key: str) -> Any:
        self.__verify_cache_integrity()
        v, _ = super().__getitem__(key)
        return v

    @override
    def get(self, key: str, default: Any = None) -> Any:  # ty: ignore[invalid-method-override]
        self.__verify_cache_integrity()
        try:
            return super().__getitem__(key)[0]
        except KeyError:
            return default

    @override
    def __len__(self) -> int:
        self.__verify_cache_integrity()
        return super().__len__()

    @override
    def __iter__(self) -> Iterator[Any]:
        self.__verify_cache_integrity()
        return super().__iter__()

    @override
    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, (value, time.monotonic()))

    @override
    def values(self) -> Iterator[Any]:  # ty: ignore[invalid-method-override]
        self.__verify_cache_integrity()
        return map(operator.itemgetter(0), super().values())

    @override
    def items(self) -> Iterator[tuple[Any, Any]]:  # ty: ignore[invalid-method-override]
        self.__verify_cache_integrity()
        return ((k, v) for k, (v, _) in super().items())


class Strategy(enum.Enum):
    """How ``cache`` keeps its results.

    Attributes
    ----------
    lru
        Keep the most recently used results, up to ``maxsize`` of them.
    raw
        Keep every result forever.
    timed
        Keep a result for ``maxsize`` seconds, counting from the start of the call.
    """

    lru = 1
    raw = 2
    timed = 3


def _no_stats() -> tuple[int, int]:
    return 0, 0


def cache[R](
    maxsize: int = 128,
    strategy: Strategy = Strategy.lru,
    *,
    ignore_kwargs: bool = False,
) -> Callable[[Callable[..., Coroutine[Any, Any, R]]], CacheProtocol[R]]:
    """Cache the results of an async function by its arguments.

    What is cached is the ``asyncio.Task`` of the call, so concurrent calls with the same arguments share one task.
    A task that failed or got cancelled is dropped from the cache, only successful results are remembered.

    Parameters
    ----------
    maxsize
        The amount of results to keep for ``Strategy.lru``, the time to live in seconds for ``Strategy.timed``
        and unused for ``Strategy.raw``.
    strategy
        How the results are kept.
    ignore_kwargs
        Leave the keyword arguments out of the cache key.

    Returns
    -------
    Callable[[Callable[..., Coroutine[Any, Any, R]]], CacheProtocol[R]]
        The decorator, the decorated function returns a task instead of a coroutine.

    Notes
    -----
    The task is shared, so cancelling it (e.g. with a timeout from ``asyncio.wait_for``) cancels it for everyone
    who awaits it. Wrap the call into ``asyncio.shield`` when that is a concern.
    """

    def decorator(func: Callable[..., Coroutine[Any, Any, R]]) -> CacheProtocol[R]:
        match strategy:
            case Strategy.lru:
                internal_cache = LRU(maxsize)
                stats = internal_cache.get_stats
            case Strategy.raw:
                internal_cache = {}
                stats = _no_stats
            case Strategy.timed:
                internal_cache = ExpiringCache(maxsize)
                stats = _no_stats
            case _:
                assert_never(strategy)

        def _make_key(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
            # this is a bit of a cluster fuck
            # we do care what 'self' parameter is when we __repr__ it
            def _true_repr(o: Any) -> str:
                if o.__class__.__repr__ is object.__repr__:
                    return f"<{o.__class__.__module__}.{o.__class__.__name__}>"
                return repr(o)

            key = [f"{func.__module__}.{func.__name__}"]  # ty: ignore[unresolved-attribute]
            key.extend(_true_repr(o) for o in args)
            if not ignore_kwargs:
                for k, v in sorted(kwargs.items()):  # sorted, so the order of the keyword arguments doesn't matter
                    # note: this only really works for this use case in particular
                    # I want to pass asyncpg.Connection objects to the parameters
                    # however, they use default __repr__ and I do not care what
                    # connection is passed in, so I needed a bypass.
                    if k in {"connection", "pool"}:
                        continue

                    key.extend((_true_repr(k), _true_repr(v)))

            return ":".join(key)

        def _evict_if_failed(key: str, task: asyncio.Task[R]) -> None:
            """Drop a finished task from the cache if it failed, so an error is not cached forever.

            Only successful results are worth remembering: a transient failure (e.g. a database hiccup)
            would otherwise be returned for the given key until the bot restarts.
            """
            if not task.cancelled():
                exception = task.exception()
                if exception is None:
                    return
                # reading the exception marks it as retrieved, so asyncio doesn't report it when nobody awaits the task
                log.warning(
                    "Cached call of %s failed, dropping it from the cache.",
                    func.__qualname__,  # ty: ignore[unresolved-attribute]
                    exc_info=exception,
                )
            with contextlib.suppress(KeyError):
                if internal_cache.get(key) is task:  # the key could have been invalidated and refilled meanwhile
                    del internal_cache[key]

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> asyncio.Task[R]:
            key = _make_key(args, kwargs)
            try:
                task = internal_cache[key]
            except KeyError:
                internal_cache[key] = task = asyncio.create_task(func(*args, **kwargs))
                task.add_done_callback(lambda t: _evict_if_failed(key, t))
                return task
            else:
                return task

        def _invalidate(*args: Any, **kwargs: Any) -> bool:
            try:
                del internal_cache[_make_key(args, kwargs)]
            except KeyError:
                return False
            else:
                return True

        def _invalidate_containing(key: str) -> None:
            to_remove = [k for k in internal_cache if key in k]
            for k in to_remove:
                try:
                    del internal_cache[k]
                except KeyError:
                    continue

        wrapper.cache = internal_cache  # ty: ignore[unresolved-attribute]
        wrapper.get_key = lambda *args, **kwargs: _make_key(args, kwargs)  # ty: ignore[unresolved-attribute]
        wrapper.invalidate = _invalidate  # ty: ignore[unresolved-attribute]
        wrapper.get_stats = stats  # ty: ignore[unresolved-attribute]
        wrapper.invalidate_containing = _invalidate_containing  # ty: ignore[unresolved-attribute]
        return wrapper  # ty: ignore[invalid-return-type]

    return decorator
