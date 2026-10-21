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
import re
import sysconfig
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
    Also logs the exceptions to the console. For some reason, default implementation of discord.py and similar libraries
    silently ignored the errors. This class in combination with error handlers (e.g. command error/event error/task error)
    make sure everything is both logged to the console and sent to the developers.

    This class handles cooldowns with a simple lock, so we don't have to worry about rate limiting our webhook (as long as
    we don't use it elsewhere).

    Attributes
    ----------
    webhook_url
        The error webhook used to send errors.
        Webhook in hideout server to send errors/notifications to the developer(-s).
    ping_role_mention
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
        "_shorten_re",
        "_shortenings",
        "cooldown",
        "error_webhook",
        "ping_role_mention",
    )

    def __init__(
        self,
        bot_base: BotBase,
        webhook_url: str,
        *,
        cooldown: dt.timedelta = dt.timedelta(seconds=5),
    ) -> None:
        """Init.

        Parameters
        ----------
        bot_base
            Bot base, it just has convenience method to create a discord webhook from url.
        webhook_url
            The error webhook used to send errors.
            Webhook in hideout server to send errors/notifications to the developer(-s).
        cooldown
            The cooldown between sending errors. This defaults to 5 seconds.
        """
        self.error_webhook: discord.Webhook = bot_base.webhook_from_url(webhook_url)
        self.ping_role_mention: str = bot_base.ping_role_mention
        self.cooldown: dt.timedelta = cooldown

        self._lock: asyncio.Lock = asyncio.Lock()
        self._most_recent: dt.datetime | None = None

        self._shortenings = {
            sysconfig.get_paths()["purelib"]: "<venv>",
            sysconfig.get_paths()["stdlib"]: "<stdlib>",
            str(Path.cwd() / "src"): "<src>",
        }
        self._shorten_re = re.compile("|".join(map(re.escape, self._shortenings)))

    @staticmethod
    def _yield_code_chunks(text: str, *, chunks_size: int = 2000) -> Generator[str]:
        prefix, suffix = "```py\n", "```"
        max_chars = chunks_size - len(prefix) - len(suffix)

        for i in range(0, len(text), max_chars):
            yield f"{prefix}{text[i : i + max_chars]}{suffix}"

    async def register(self, error: BaseException, embed: discord.Embed) -> None:
        """Register, analyse error and put it into queue to send to developers.

        Parameters
        ----------
        error
            The error to register.
        embed
            Discord Embed to send together with the error's traceback.
            This should showcase some information that can't be gotten from the error object directly, i.e.
            discord author information, guild where the error happened, some snowflakes, etc.
        """
        log.error("⛔ Registering %s", error.__class__.__name__, exc_info=error)

        traceback_string = self._shorten_re.sub(
            repl=lambda mo: self._shortenings[mo.group()],
            string="".join(traceback.format_exception(error)),
        )

        async with self._lock:
            if self._most_recent and (elapsed := clock.utcnow() - self._most_recent) < self.cooldown:
                remaining = (self.cooldown - elapsed).total_seconds()
                log.debug("Waiting %.2f seconds to send the error.", remaining)
                await asyncio.sleep(remaining)

            self._most_recent = clock.utcnow()
            try:
                await self._send_notification(traceback_string, embed)
            except Exception:
                log.exception("Failed to send error notification")

    async def _send_notification(self, traceback_string: str, embed: discord.Embed) -> None:
        """Send an error notification to the webhook.

        This pings the developers with `self.ping_role_mention` mention.

        .. caution::

            It is not recommended to call this yourself, call `register` instead.

        Parameters
        ----------
        traceback_string
            The traceback of the error.
        embed
            Discord Embed to send together with the traceback. This comes from registering the error.
        """
        code_chunks = list(self._yield_code_chunks(traceback_string))

        await self.error_webhook.send(self.ping_role_mention)
        for chunk in code_chunks:
            await self.error_webhook.send(chunk)
        await self.error_webhook.send(embed=embed)
