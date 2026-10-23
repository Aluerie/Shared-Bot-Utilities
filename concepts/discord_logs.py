"""Discord Webhook Logger.

Mirror records from the standard `logging` machinery into a Discord webhook channel.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

import asyncio
import datetime as dt
import logging
import traceback
from typing import TYPE_CHECKING, ClassVar, override

import discord
from discord.utils import MISSING

from shared import clock
from shared.concepts import loop

if TYPE_CHECKING:
    from aiohttp import ClientSession


log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


class LoggingHandler(logging.Handler):
    """Logging handler that forwards INFO+ records to `DiscordWebhookLogs`.

    The handler does no formatting or I/O itself. It only decides which records are worth mirroring and
    hands them to the owner's queue, so it's safe to attach to the root logger.

    Parameters
    ----------
    cog
        The owner that queues, rate-limits and sends the records.
    """

    def __init__(self, cog: DiscordWebhookLogs) -> None:
        self.cog: DiscordWebhookLogs = cog
        super().__init__(logging.INFO)

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        """Decide whether a record should be mirrored to Discord.

        Drops known noisy messages so they don't flood the channel.

        Returns
        -------
        `True` to mirror the record, `False` to discard it.
        """
        messages_to_ignore = (
            self.cog.rate_limit_message,
            "Clock drift detected for task",  # I'm not sure how to fix this Discord.py warning
        )
        return not any(msg and msg in record.getMessage() for msg in messages_to_ignore)

    @override
    def emit(self, record: logging.LogRecord) -> None:
        """Pass an accepted record to the owner's queue without blocking."""
        self.cog.add_record(record)


class DiscordWebhookLogs:
    """Mirror log records to a Discord webhook as embeds.

    Records are queued by `LoggingHandler` and sent one at a time by a background worker. The worker
    waits at least `cooldown` between sends to stay under Discord's webhook rate limits.

    Parameters
    ----------
    webhook_url
        URL of the webhook to send logs to.
    session
        HTTP session used by the webhook. Its lifetime is managed by the caller.

    Attributes
    ----------
    EXACT_AVATAR_MAPPING
        Logger name -> avatar URL, matched exactly.
    INCLUSIVE_AVATAR_MAPPING
        Logger name prefix -> avatar URL, matched with `str.startswith`.
    LEVEL_EMOJIS
        Level name -> emoji shown at the start of the message.
    cooldown
        Minimum time between two webhook sends.
    extra_exact_avatar_mapping
        Runtime additions to `EXACT_AVATAR_MAPPING`. Entries here take priority.
    rate_limit_message
        Text of discord.py's rate-limit warning for this webhook. Set in `load`, and records containing it
        are filtered out.
    """

    EXACT_AVATAR_MAPPING: ClassVar[dict[str, str]] = {
        "error_notification_manager": "https://em-content.zobj.net/source/microsoft/378/sos-button_1f198.png",
    }
    INCLUSIVE_AVATAR_MAPPING: ClassVar[dict[str, str]] = {
        "twitchio.": "https://raw.githubusercontent.com/Aluerie/AluBot/main/assets/images/logo/twitchio.png",
        "discord.": "https://cdn.discordapp.com/icons/336642139381301249/3aa641b21acded468308a37eef43d7b3.png?size=256",
    }

    LEVEL_EMOJIS: ClassVar[dict[str, str]] = {
        "INFO": "\N{INFORMATION SOURCE}\ufe0f",
        "WARNING": "\N{WARNING SIGN}\ufe0f",
        "ERROR": "\N{CROSS MARK}",
        "CRITICAL": "\N{COLLISION SYMBOL}",
    }

    def __init__(self, webhook_url: str, session: ClientSession) -> None:
        self.webhook_url: str = webhook_url
        self.session: ClientSession = session

        self._logging_queue: asyncio.Queue[logging.LogRecord] = asyncio.Queue()
        self._lock: asyncio.Lock = asyncio.Lock()
        self.cooldown: dt.timedelta = dt.timedelta(seconds=5)
        self._most_recent: dt.datetime | None = None
        self.logs_handler = LoggingHandler(self)

        self.rate_limit_message: str = ""
        self.extra_exact_avatar_mapping: dict[str, str] = {}

    @discord.utils.cached_property
    def logger_webhook(self) -> discord.Webhook:
        """Webhook that log records are sent to, built lazily from `webhook_url`."""
        return discord.Webhook.from_url(self.webhook_url, session=self.session)

    async def load(self) -> None:
        """Start mirroring logs."""
        self.rate_limit_message = f"Webhook ID {self.logger_webhook.id} is rate limited."
        self.logging_worker.start()
        logging.getLogger().addHandler(self.logs_handler)

    async def teardown(self) -> None:
        """Stop mirroring logs."""
        self.logging_worker.stop()
        logging.getLogger().removeHandler(self.logs_handler)
        del self.logs_handler

    def add_record(self, record: logging.LogRecord) -> None:
        """Queue a record for the worker to send. Never blocks."""
        self._logging_queue.put_nowait(record)

    def get_avatar(self, username: str) -> str:
        """Pick the avatar URL for a webhook message.

        Exact matches (`extra_exact_avatar_mapping` over `EXACT_AVATAR_MAPPING`) win over prefix matches
        in `INCLUSIVE_AVATAR_MAPPING`.

        Parameters
        ----------
        username
            Name the webhook message is sent under, which is the logger name.

        Returns
        -------
        The avatar URL, or `MISSING` to use the webhook's default avatar.
        """
        # exact name
        if (avatar_url := (self.EXACT_AVATAR_MAPPING | self.extra_exact_avatar_mapping).get(username)) is not None:
            return avatar_url
        # inclusions
        for search_name, candidate in self.INCLUSIVE_AVATAR_MAPPING.items():
            if username.startswith(search_name):
                return candidate
        # else
        return MISSING

    async def send_log_record(self, record: logging.LogRecord) -> None:
        """Send Log record to discord webhook as a plain message."""
        emoji = self.LEVEL_EMOJIS.get(record.levelname, "\N{WHITE QUESTION MARK ORNAMENT}")
        record_dt = dt.datetime.fromtimestamp(record.created, dt.UTC)
        text = f"{emoji} {discord.utils.format_dt(record_dt, style='T')} {record.getMessage()}"
        content = text if len(text) <= 2000 else text[:1999] + "…"
        await self.logger_webhook.send(
            content=content,
            username=record.name.replace("discord", "dpy")[:80],  # Discord disallows usernames containing "discord"
            avatar_url=self.get_avatar(record.name),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @loop(seconds=0.0)
    async def logging_worker(self) -> None:
        """Take the next queued record and send it, respecting `cooldown`."""
        record = await self._logging_queue.get()

        async with self._lock:
            if self._most_recent and (elapsed := clock.utcnow() - self._most_recent) < self.cooldown:
                # We have to wait
                total_seconds = (self.cooldown - elapsed).total_seconds()
                log.debug("Waiting %.2f seconds to send the record.", total_seconds)
                await asyncio.sleep(total_seconds)

            self._most_recent = clock.utcnow()
            try:
                await self.send_log_record(record)
            except Exception:  # ruff: ignore[blind-except]
                traceback.print_exc()
