"""Utilities.

The name `ut.py` is a bit silly, but it's meant to be a very short of "utilities".

This module contains some utilities that I could not categorize anywhere.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import TYPE_CHECKING, Any, Self, override

if TYPE_CHECKING:
    from collections.abc import Iterable


__all__ = (
    "MISSING",
    "measure_time",
    "ni",
    "run",
)

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


try:
    import uvloop  # ty: ignore[unresolved-import, unused-ignore-comment, unused-ignore-comment]
except ModuleNotFoundError:
    # WINDOWS - uvloop does not support Windows
    run = asyncio.run
else:
    # LINUX
    run = uvloop.run


def ni[T](iterable: Iterable[T]) -> T | None:
    """Get next iter element from an iterable.

    Shortcut for ``next(iter(iterable), None)``, which is a quite common construction within this codebase.
    I'm not sure why I'm annoyed to type it out fully, but I am.
    """
    return next(iter(iterable), None)


class _MissingSentinel:
    __slots__ = ()

    @override
    def __eq__(self, other: object) -> bool:
        return False

    def __bool__(self) -> bool:
        return False

    @override
    def __hash__(self) -> int:
        return 0

    @override
    def __repr__(self) -> str:
        return "..."


MISSING: Any = _MissingSentinel()


class measure_time:  # ruff: ignore[invalid-class-name]
    """Measure performance time of a context'ed codeblock.

    Example:
    -------
    ```py
    with measure_time("My long operation"):
        time.sleep(5)

    async with measure_time("My long async operation"):
        await asyncio.sleep(5)
    ```
    It will output the perf_counter with `log.debug`.

    """

    def __init__(self, name: str = "Unnamed", *, logger: logging.Logger = log) -> None:
        self.name: str = name
        self.log: logging.Logger = logger
        self.start: float = 0.0
        self.end: float = 0.0

    def __enter__(self) -> Self:
        self.start = perf_counter()
        return self

    async def __aenter__(self) -> Self:
        self.start = perf_counter()
        return self

    def measure_time(self) -> None:
        """Record and debug-log measured PT (Performance Time).

        Notes
        -----
        * maybe there are better ideas for abbreviations than PT.
        """
        self.end = end = perf_counter() - self.start
        self.log.debug("%s PT: %.6f secs", self.name, end)

    def __exit__(self, *_: object) -> None:
        self.measure_time()

    async def __aexit__(self, *_: object) -> None:
        self.measure_time()
