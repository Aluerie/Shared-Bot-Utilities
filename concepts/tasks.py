"""Tasks.

Source
------
* `discord.ext.tasks` (MIT License)

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Sequence
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, overload, override

import discord
from discord.ext import tasks
from discord.utils import MISSING

if TYPE_CHECKING:
    import datetime as dt

    from .error_notifications import ErrorNotificationManager

    class BotWithTasksProtocol(Protocol):
        """Protocol for some methods, attributed of BotBase and Bot classes."""

        error_notification_manager: ErrorNotificationManager

        @staticmethod
        def add_codeblock_field(
            embed: discord.Embed, *, data: dict[str, Any], field_name: str = "Extra Data"
        ) -> discord.Embed: ...

        # All 3 (Discord, Twitch, Steam) bot libraries have `wait_until_ready` in the bot class - so we get to be cheeky
        async def wait_until_ready(self) -> None:
            return

    class CogWithTasksProtocol(Protocol):
        bot: BotWithTasksProtocol


# fmt: off
__all__ = (
    'loop',
)
# fmt: on


_func = Callable[..., Coroutine[Any, Any, Any]]
LF = TypeVar("LF", bound=_func)


class Loop(tasks.Loop[LF]):
    """My subclass for discord.ext.tasks.Loop.

    This extension class adds the following:
    * Error Manager Notifications;
    * `wait_for_ready` kwarg;

    Warning
    -------
    The task should be initiated in a class (e.g. Cog, Component) that has `.bot` of XxxBot type.
    Thankfully, there is no real need to use tasks outside of cogs.

    Some notes to myself that I'm not sure where else to put
    --------------------------------------------------------
    * `before_loop`/`after_loop` only happens before/after the whole "loop" task is done,
      it doesn't trigger before/after iteration. The name clearly indicates that but I got confused once.
    * `cancel` - not graceful, `stop` - graceful. I have no idea how to remember that.
    * `after_loop` will be triggered after both `stop`/`cancel`. The way to distinguish is `is_being_cancelled` property.
    """

    def __init__(
        self,
        coro: LF,
        seconds: float,
        hours: float,
        minutes: float,
        time: dt.time | Sequence[dt.time],
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

    async def _wait_for_ready(self, cog: CogWithTasksProtocol) -> None:
        """Wait for ready.

        if `wait_for_ready=True` was given to class constructor then it will be used as a `.before_loop` behavior.
        It's somewhat convenience method. Otherwise, every task would have

        .. code-block:: python

            @my_task.before_loop
            @other_task.before_loop
            async def my_task_before(self):
                await self.bot.wait_until_ready()

        fragment of code. Can still be overwritten it for custom behavior.
        """
        await cog.bot.wait_until_ready()

    @override
    async def _error(self, cog: CogWithTasksProtocol, exception: Exception) -> None:  # ty: ignore[invalid-method-override]
        """Register exceptions in tasks with our `error_notification_manager`."""
        embed = discord.Embed(
            colour=0x1A7A8A,
            title=f"Task Error `{getattr(self.coro, '__qualname__', 'unknown coro')}`",
        )
        if debug_data := getattr(exception, "debug_data", None):
            embed = cog.bot.add_codeblock_field(embed, data=debug_data)
        await cog.bot.error_notification_manager.register(exception, embed)


@overload
def loop(
    *,
    seconds: float = 0,
    minutes: float = 0,
    hours: float = 0,
    count: int | None = None,
    reconnect: bool = True,
    name: str | None = None,
    wait_for_ready: bool = False,
) -> Callable[[LF], Loop[LF]]: ...


@overload
def loop(
    *,
    time: dt.time | Sequence[dt.time],
    count: int | None = None,
    reconnect: bool = True,
    name: str | None = None,
    wait_for_ready: bool = False,
) -> Callable[[LF], Loop[LF]]: ...


@discord.utils.copy_doc(tasks.loop)
def loop(
    *,
    seconds: float = MISSING,
    minutes: float = MISSING,
    hours: float = MISSING,
    time: dt.time | Sequence[dt.time] = MISSING,
    count: int | None = None,
    reconnect: bool = True,
    name: str | None = None,
    wait_for_ready: bool = False,
) -> Callable[[LF], Loop[LF]]:
    """Copy-pasted `loop` decorator from `discord.ext.tasks` corresponding to AluLoop class.

    .. warning::

        * if `discord.ext.tasks` gets extra cool features which will be represented in a change of `tasks.loop`
          decorator/signature we would need to manually update this function and/or Loop class)

    """

    def decorator(func: LF) -> Loop[LF]:
        return Loop(
            coro=func,
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
