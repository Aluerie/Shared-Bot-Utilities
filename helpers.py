"""Helpers.

Some utilities that I could not categorize anywhere really.
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Self, override

__all__ = ("measure_time",)

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


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


# TODO: I think python 3.15 provides a natural solution to this?
MISSING: Any = _MissingSentinel()


class measure_time:  # noqa: N801 # it's fine to call classes lowercase if they aren't used as actual classes per PEP-8.
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
