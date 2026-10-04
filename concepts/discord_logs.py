"""Discord Webhook Logger.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import textwrap
from typing import TYPE_CHECKING, ClassVar, override

import discord
from discord.utils import MISSING

from core import ireloop
from shared import clock

if TYPE_CHECKING:
    from aiohttp import ClientSession


log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


class LoggingHandler(logging.Handler):
    """Extra Logging Handler to output info/warning/errors to a discord webhook."""

    def __init__(self, cog: DiscordWebhookLogs) -> None:
        self.cog: DiscordWebhookLogs = cog
        super().__init__(logging.INFO)

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        """Filter out some somewhat pointless messages so we don't spam the channel as much."""
        messages_to_ignore = ("Webhook ID 1280488051776163903 is rate limited.",)
        return not any(msg in record.message for msg in messages_to_ignore)

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.cog.add_record(record)


class DiscordWebhookLogs:
    """Mirroring logs to discord webhook messages.

    This cog is responsible for rate-limiting, formatting, fine-tuning and sending the log messages.
    """

    EXACT_AVATAR_MAPPING: ClassVar[dict[str, str]] = {
        "exc_manager": "https://em-content.zobj.net/source/microsoft/378/sos-button_1f198.png",
    }
    INCLUSIVE_AVATAR_MAPPING: ClassVar[dict[str, str]] = {
        "twitchio.": "https://raw.githubusercontent.com/Aluerie/AluBot/main/assets/images/logo/twitchio.png"
    }

    LEVEL_EMOJIS: ClassVar[dict[str, str]] = {
        "INFO": "\N{INFORMATION SOURCE}\ufe0f",
        "WARNING": "\N{WARNING SIGN}\ufe0f",
        "ERROR": "\N{CROSS MARK}",
    }
    LEVEL_COLORS: ClassVar[dict[str, discord.Color | int]] = {
        "INFO": 0x03A9F4,
        "WARNING": 0xFBC02D,
        "ERROR": 0x800000,
    }

    def __init__(self, webhook_url: str, session: ClientSession) -> None:
        self.webhook_url: str = webhook_url
        self.session: ClientSession = session

        self._logging_queue: asyncio.Queue[logging.LogRecord] = asyncio.Queue()
        self._lock: asyncio.Lock = asyncio.Lock()
        self.cooldown: dt.timedelta = dt.timedelta(seconds=5)
        self._most_recent: dt.datetime | None = None
        self.logs_handler = LoggingHandler(self)

        self.extra_exact_avatar_mapping: dict[str, str] = {}

    @discord.utils.cached_property
    def logger_webhook(self) -> discord.Webhook:
        """Webhook in hideout's #logger channel."""
        return discord.Webhook.from_url(self.webhook_url, session=self.session)

    async def load(self) -> None:
        """Load Discord Webhook Logger."""
        self.logging_worker.start()
        logging.getLogger().addHandler(self.logs_handler)

    async def teardown(self) -> None:
        """Teardown Discord Webhook Logger."""
        self.logging_worker.stop()
        logging.getLogger().removeHandler(self.logs_handler)
        del self.logs_handler

    def add_record(self, record: logging.LogRecord) -> None:
        """Add a record to a logging queue."""
        self._logging_queue.put_nowait(record)

    def get_avatar(self, username: str) -> str:
        """Fet an avatar_ulr based on a webhook username to send the record with."""
        # exact name
        if avatar_url := (self.extra_exact_avatar_mapping | self.EXACT_AVATAR_MAPPING).get(username):
            return avatar_url
        # inclusions
        for search_name, candidate in self.INCLUSIVE_AVATAR_MAPPING.items():
            if username.startswith(search_name):
                return candidate
        # else
        return MISSING

    async def send_log_record(self, record: logging.LogRecord) -> None:
        """Send Log record to discord webhook."""
        emoji = self.LEVEL_EMOJIS.get(record.levelname, "\N{WHITE QUESTION MARK ORNAMENT}")
        record_dt = dt.datetime.fromtimestamp(record.created, dt.UTC)
        embed = discord.Embed(
            color=self.LEVEL_COLORS.get(record.levelname),
            description=textwrap.shorten(
                f"{emoji} {discord.utils.format_dt(record_dt, style='T')} {record.message}", width=1995
            ),
        )
        await self.logger_webhook.send(
            embed=embed,
            username=record.name.replace("discord", "dpy"),  # Discord disallows usernames containing "discord"
            avatar_url=self.get_avatar(record.name),
        )

    @ireloop(seconds=0.0)
    async def logging_worker(self) -> None:
        """Task responsible for mirroring logging messages to a discord webhook."""
        record = await self._logging_queue.get()

        async with self._lock:
            if self._most_recent and (delta := clock.utcnow() - self._most_recent) < self.cooldown:
                # We have to wait
                total_seconds = delta.total_seconds()
                log.debug("Waiting %.2f seconds to send the record.", total_seconds)
                await asyncio.sleep(total_seconds)

            self._most_recent = clock.utcnow()
            await self.send_log_record(record)
