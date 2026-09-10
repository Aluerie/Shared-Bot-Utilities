from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine, Sequence
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

import discord
from discord.ext import tasks
from discord.utils import MISSING

if TYPE_CHECKING:
    import datetime

    from core import IreBot

    class HasBotAttribute(Protocol):
        bot: IreBot


log = logging.getLogger(__name__)

__all__ = ("CustomLoop", "custom_loop")


_func = Callable[..., Coroutine[Any, Any, Any]]
LF = TypeVar("LF", bound=_func)


class CustomLoop(tasks.Loop[LF]):
    """My subclass for discord.ext.tasks.Loop.

    Just extra boilerplate functionality.

    Warning
    -------
    The task should be initiated in a class that has `.bot` of IreBot type. Otherwise, it will just fail.
    All my tasks (and all my code is in cogs that do have `.bot` but still)

    """

    def __init__(
        self,
        coro: LF,
        seconds: float,
        hours: float,
        minutes: float,
        time: datetime.time | Sequence[datetime.time],
        count: int | None,
        *,
        reconnect: bool,
        name: str | None,
        wait_for_ready: bool = False,
    ) -> None:
        super().__init__(coro, seconds, hours, minutes, time, count, reconnect, name)
        if wait_for_ready:
            self._before_loop = self._wait_for_ready

        # Not sure how I feel about it, but it's annoying that it silences `aiohttp.ClientError, asyncio.TimeoutError`
        # because valid aiohttp requests raise them as well !
        self.clear_exception_types()

    async def _wait_for_ready(self, *args: Any) -> None:
        pass


@discord.utils.copy_doc(tasks.loop)
def custom_loop(
    *,
    seconds: float = MISSING,
    minutes: float = MISSING,
    hours: float = MISSING,
    time: datetime.time | Sequence[datetime.time] = MISSING,
    count: int | None = None,
    reconnect: bool = True,
    name: str | None = None,
    wait_for_ready: bool = False,
) -> Callable[[LF], CustomLoop[LF]]:
    """Copy-pasted `loop` decorator from `discord.ext.tasks` corresponding to AluLoop class.

    Notes
    -----
    * if `discord.ext.tasks` gets extra cool features which will be represented in a change of `tasks.loop`
        decorator/signature we would need to manually update this function (or maybe even AluLoop class)

    """

    def decorator(func: LF) -> CustomLoop[LF]:
        return CustomLoop(
            func,
            seconds=seconds,
            minutes=minutes,
            hours=hours,
            count=count,
            time=time,
            reconnect=reconnect,
            name=name,
            wait_for_ready=wait_for_ready,
        )

    return decorator
