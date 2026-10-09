"""Error Notification Manager.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import platform
import re
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

from shared import clock

if TYPE_CHECKING:
    from collections.abc import Generator

    import discord

    from .base_bot import BotBase

__all__ = ("ErrorNotificationManager",)

log = logging.getLogger("error_notification_manager")


class ErrorNotificationManager:
    """Error Notification Manager.

    This sends all exceptions to a discord webhook with a role-ping so developers are notified as quickly as possible.
    Also logs the exceptions to the console. For some reason, default implementation of discord.py and similar libraries is
    to silently ignore the errors. This class in combination with error handlers (e.g. command error/event error/task error)
    make sure everything is logged to the console and sent to the developers.

    This class handles cooldowns with a simple lock, so we don't have to worry about rate limiting our webhook (as long as
    we don't use it elsewhere).

    Attributes
    ----------
    bot_base
        Bot base, it just has convenience method to create a discord webhook from url.
    webhook_url
        The error webhook used to send errors.
        Webhook in hideout server to send errors/notifications to the developer(-s).
    ping
        Discord mention of the role to ping the developers with.
    cooldown
        The cooldown between sending errors. This defaults to 5 seconds.

    Source and inspirations
    -----------------------
    DuckBot (MPL 2.0 License) by @LeoCx1000 and others
    * https://github.com/DuckBot-Discord/DuckBot/blob/rewrite/utils/errorhandler.py
    """

    __slots__: tuple[str, ...] = (
        "_lock",
        "_most_recent",
        "cooldown",
        "error_webhook",
        "ping",
    )

    def __init__(
        self,
        bot_base: BotBase,
        webhook_url: str,
        ping: str,
        *,
        cooldown: dt.timedelta = dt.timedelta(seconds=5),
    ) -> None:
        self.error_webhook: discord.Webhook = bot_base.webhook_from_url(webhook_url)
        self.ping: str = ping
        self.cooldown: dt.timedelta = cooldown

        self._lock: asyncio.Lock = asyncio.Lock()
        self._most_recent: dt.datetime | None = None

    def _yield_code_chunks(self, iterable: str, *, chunks_size: int = 2000) -> Generator[str]:
        codeblocks: str = "```py\n{}```"
        max_chars_in_code: int = chunks_size - (len(codeblocks) - 2)  # chunks_size minus code blocker size

        for i in range(0, len(iterable), max_chars_in_code):
            yield codeblocks.format(iterable[i : i + max_chars_in_code])

    async def register(self, error: BaseException, embed: discord.Embed) -> None:
        """Register, analyse error and put it into queue to send to developers.

        Parameters
        ----------
        error
            The error to register.
        embed
            Discord Embed to send together with the error's traceback.
        """
        log.error("⛔ Registering %s", error.__class__.__name__, exc_info=error)

        if platform.system() == "Linux":
            py_version = sys.version_info
            venv_path = f"{Path.cwd()}/.venv/lib/python{py_version.major}.{py_version.minor}/site-packages"
            src_path = f"{Path.cwd()}/src"
        else:
            # Windows (fok MacOS)
            venv_path = f"{Path.cwd()}\\.venv\\Lib\\site-packages"
            src_path = f"{Path.cwd()}\\src"

        shortenings = {venv_path: "<venv>", src_path: "<src>"}
        regex_pattern = re.compile("|".join(map(re.escape, shortenings.keys())))
        traceback_string = regex_pattern.sub(
            repl=lambda mo: shortenings[mo.group()],
            string="".join(traceback.format_exception(error)),
        )

        async with self._lock:
            if self._most_recent and (delta := clock.utcnow() - self._most_recent) < self.cooldown:
                # We have to wait
                total_seconds = delta.total_seconds()
                log.debug("Waiting %s seconds to send the error.", total_seconds)
                await asyncio.sleep(total_seconds)

            self._most_recent = clock.utcnow()
            await self._send_notification(traceback_string, embed)

    async def _send_notification(self, traceback: str, embed: discord.Embed) -> None:
        """Send an error notification to the webhook.

        This pings the developers with `self.ping` mention.

        .. caution::

            It is not recommended to call this yourself, call `register` instead.

        Parameters
        ----------
        traceback: :class:`str`
            The traceback of the error.
        embed
            Discord Embed to send together with the traceback.
        """
        code_chunks = list(self._yield_code_chunks(traceback))

        await self.error_webhook.send(self.ping)
        for chunk in code_chunks:
            await self.error_webhook.send(chunk)
        await self.error_webhook.send(embed=embed)
