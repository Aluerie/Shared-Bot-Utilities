# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Tasks.

References
----------
* :mod:`discord.ext.tasks` (MIT License)
"""

import types
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, Protocol, overload, override

import discord
from discord.ext import tasks
from discord.utils import MISSING

from shared import errors, fmt

if TYPE_CHECKING:
    import datetime as dt
    from collections.abc import Sequence

    from discord.ext.tasks import Loop as DiscordLoop

    from .error_notifications import ErrorNotificationManager

    class BotWithTasksProtocol(Protocol):
        """Protocol for some methods, attributed of BotBase and Bot classes."""

        error_notification_manager: ErrorNotificationManager

        # All 3 (Discord, Twitch, Steam) bot libraries have `wait_until_ready` in the bot class - so we get to be cheeky
        async def wait_until_ready(self) -> None: ...

    class CogWithTasksProtocol(Protocol):
        bot: BotWithTasksProtocol


__all__ = (
    "Loop",
    "loop",
    "restart_task",
)


type _Func = Callable[..., Coroutine[Any, Any, Any]]


class Loop[LF: _Func](tasks.Loop[LF]):
    """My subclass for :class:`discord.ext.tasks.Loop`.

    This extension class adds the following:

    * Error manager notifications.
    * ``wait_for_ready`` keyword argument, which can be combined with ``before_loop``: the bot gets ready first,
      then the hook runs.
    * No silenced exception types: network errors reach ``_error`` instead of being retried.

    .. warning::

        The task should be initiated in a class (e.g. Cog, Component) that has ``.bot`` of Bot type.
        Thankfully, there is no real need to use tasks outside of cogs.

    .. note::

        * ``before_loop``/``after_loop`` only happen before/after the whole loop task is done,
          they don't trigger before/after each iteration. The name clearly indicates that but I got confused once.
        * ``cancel`` is not graceful, ``stop`` is graceful. I have no idea how to remember that.
        * ``after_loop`` is triggered after both ``stop`` and ``cancel``.
          The way to distinguish is the ``is_being_cancelled`` property.
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
        self._wait_for_ready_enabled: bool = wait_for_ready
        self._user_before_loop: _Func | None = None
        if wait_for_ready:
            self._before_loop = self._wait_for_ready_then_user_hook

        # it's annoying that discord silences `aiohttp.ClientError` and `asyncio.TimeoutError` by default,
        # because valid aiohttp requests raise them as well and they should reach `_error`.
        # A task can opt back in with `add_exception_type` right after its definition.
        self.clear_exception_types()

    @override
    def __get__(self, obj: Any, objtype: Any) -> DiscordLoop[LF]:
        """Apply per-instance settings that discord's descriptor drops when it copies the task.

        :meth:`discord.ext.tasks.Loop.__get__` builds a plain :class:`discord.ext.tasks.Loop` for every instance and
        carries over only the loop hooks, which stay bound to this template task. So the exception types
        (``_valid_exception``) are copied over, and ``_error`` is rebound to the copy so that it reads the copy's
        own state (``current_loop``, ``next_iteration``). The copy is stored on the instance, so this runs once per
        instance and task.

        Parameters
        ----------
        obj
            The instance the task is accessed on, or ``None`` when it is accessed on the class.
        objtype
            The class the task is accessed on.
        """
        loop_copy = super().__get__(obj, objtype)
        if obj is not None:
            loop_copy._valid_exception = self._valid_exception  # ruff: ignore[private-member-access]
            bound_error = types.MethodType(type(self)._error, loop_copy)  # ruff: ignore[private-member-access]
            loop_copy._error = bound_error  # ty: ignore[invalid-assignment]  # ruff: ignore[private-member-access]
        return loop_copy

    @override
    def before_loop(self, coro: Any) -> Any:
        """Register a hook that runs before the loop starts.

        With ``wait_for_ready=True`` the hook runs after the bot is ready, so it doesn't need to wait for it itself.

        Parameters
        ----------
        coro
            The coroutine function to run as the hook.
        """
        result = super().before_loop(coro)
        self._user_before_loop = coro
        if self._wait_for_ready_enabled:
            # `super().before_loop` replaces `_before_loop` with the user's hook, so put ours back.
            self._before_loop = self._wait_for_ready_then_user_hook
        return result

    async def _wait_for_ready_then_user_hook(self, cog: CogWithTasksProtocol) -> None:
        """Wait for ready, then run the hook registered with ``before_loop``, if any.

        This is the ``before_loop`` behavior of tasks with ``wait_for_ready=True``. It's somewhat convenience method.
        Otherwise, every task would have

        .. code-block:: python

            @my_task.before_loop
            @other_task.before_loop
            async def my_task_before(self):
                await self.bot.wait_until_ready()

        fragment of code.
        """
        await cog.bot.wait_until_ready()
        if self._user_before_loop is not None:
            await self._user_before_loop(cog)

    @override
    async def _error(self, cog: CogWithTasksProtocol, exception: Exception) -> None:  # ty: ignore[invalid-method-override]
        """Register exceptions in tasks with our ``error_notification_manager``."""
        embed = discord.Embed(
            colour=0x1A7A8A,
            title=f"Task Error `{getattr(self.coro, '__qualname__', 'unknown coro')}`",
            description="The task has stopped and will not run again until restarted.",
        )
        fmt.add_mapping_field(
            embed,
            "Loop State",
            {"current_loop": self.current_loop, "next_iteration": self.next_iteration, "count": self.count},
        )
        if isinstance(exception, errors.BotError) and exception.data:
            fmt.add_mapping_field(embed, "Bot", exception.data)
        await cog.bot.error_notification_manager.register(exception, embed)


@overload
def loop[LF: _Func](
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
def loop[LF: _Func](
    *,
    time: dt.time | Sequence[dt.time],
    count: int | None = None,
    reconnect: bool = True,
    name: str | None = None,
    wait_for_ready: bool = False,
) -> Callable[[LF], Loop[LF]]: ...


# Copy-pasted `loop` decorator from `discord.ext.tasks` corresponding to Loop class.
#
# Warning
# -------
# if `discord.ext.tasks` gets extra cool features which will be represented in a change of `tasks.loop`
# decorator/signature we would need to manually update this function and/or Loop class)
@discord.utils.copy_doc(tasks.loop)
def loop[LF: _Func](
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
    """Loop."""

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


def restart_task(task: DiscordLoop[Any], *args: Any) -> None:
    """Start a task, or restart it from the beginning if it is already running.

    Calling :meth:`~discord.ext.tasks.Loop.restart` on a task that is not running does nothing, hence the check.

    Parameters
    ----------
    task
        The task to start or restart.
    *args
        Arguments to pass to the task.
    """
    if task.is_running():
        task.restart(*args)
    else:
        task.start(*args)
