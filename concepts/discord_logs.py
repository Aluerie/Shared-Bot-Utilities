# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Discord Webhook Logger.

Mirror loguru records (which include the standard `logging` records of libraries, see `logs.InterceptHandler`)
into a Discord webhook channel.
"""

import asyncio
import datetime as dt
import traceback
from typing import TYPE_CHECKING, ClassVar, Final

import discord
from discord.utils import MISSING
from loguru import logger

from shared import clock
from shared.concepts import loop

if TYPE_CHECKING:
    from aiohttp import ClientSession
    from loguru import Message, Record


class DiscordWebhookLogs:
    """Mirror log records to a Discord webhook as embeds.

    Records are queued by a loguru sink (added in `load`) and sent one at a time by a background worker. The worker
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
    cooldown
        Minimum time between two webhook sends.
    extra_exact_avatar_mapping
        Runtime additions to `EXACT_AVATAR_MAPPING`. Entries here take priority.
    rate_limit_message
        Text of discord.py's rate-limit warning for this webhook. Set in `load`, and records containing it
        are filtered out.
    """

    EXACT_AVATAR_MAPPING: Final[dict[str, str]] = {
        "error_notification_manager": "https://em-content.zobj.net/source/microsoft/378/sos-button_1f198.png",
    }
    INCLUSIVE_AVATAR_MAPPING: Final[dict[str, str]] = {
        "twitchio.": "https://raw.githubusercontent.com/Aluerie/AluBot/main/assets/images/logo/twitchio.png",
        "discord.": "https://cdn.discordapp.com/icons/336642139381301249/3aa641b21acded468308a37eef43d7b3.png?size=256",
    }
    EXTRA_EXACT_AVATAR_MAPPING: ClassVar[dict[str, str]] = {}

    def __init__(self, webhook_url: str, session: ClientSession) -> None:
        self.webhook_url: str = webhook_url
        self.session: ClientSession = session

        self._logging_queue: asyncio.Queue[Record] = asyncio.Queue()
        self._lock: asyncio.Lock = asyncio.Lock()
        self.cooldown: dt.timedelta = dt.timedelta(seconds=5)
        self._most_recent: dt.datetime | None = None
        self._sink_id: int | None = None

        self.rate_limit_message: str = ""
        self._event_loop: asyncio.AbstractEventLoop | None = None

    @discord.utils.cached_property
    def logger_webhook(self) -> discord.Webhook:
        """Webhook that log records are sent to, built lazily from `webhook_url`."""
        return discord.Webhook.from_url(self.webhook_url, session=self.session)

    async def load(self) -> None:
        """Start mirroring logs."""
        self.rate_limit_message = f"Webhook ID {self.logger_webhook.id} is rate limited."
        self._event_loop = asyncio.get_running_loop()
        self.logging_worker.start()
        self._sink_id = logger.add(self._sink, level="INFO", filter=self._filter, format="{message}")

    async def teardown(self) -> None:
        """Stop mirroring logs."""
        self.logging_worker.stop()
        if self._sink_id is not None:
            logger.remove(self._sink_id)
            self._sink_id = None

    def _filter(self, record: Record) -> bool:
        """Decide whether a record should be mirrored to Discord.

        Drops known noisy messages so they don't flood the channel.

        Returns
        -------
        bool
            `True` to mirror the record, `False` to discard it.
        """
        messages_to_ignore = (
            self.rate_limit_message,
            "Clock drift detected for task",  # I'm not sure how to fix this Discord.py warning
        )
        return not any(msg and msg in record["message"] for msg in messages_to_ignore)

    def _sink(self, message: Message) -> None:
        """Loguru sink: pass an accepted record to the queue without blocking. No formatting or I/O here."""
        self.add_record(message.record)

    def add_record(self, record: Record) -> None:
        """Queue a record for the worker to send. Never blocks.

        Records can be logged from any thread (e.g. `asyncio.to_thread`, executors, library threads),
        but `asyncio.Queue` is not thread-safe, so records from other threads are handed over to the event loop.
        """
        event_loop = self._event_loop
        if event_loop is None:
            return  # not loaded yet
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is event_loop:
            self._logging_queue.put_nowait(record)
            return
        try:
            event_loop.call_soon_threadsafe(self._logging_queue.put_nowait, record)
        except RuntimeError:
            # the event loop is closed (e.g. a thread logs during shutdown), there is nobody to send the record
            return

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
        str
            The avatar URL, or `MISSING` to use the webhook's default avatar.
        """
        # exact name
        if (avatar_url := (self.EXACT_AVATAR_MAPPING | self.EXTRA_EXACT_AVATAR_MAPPING).get(username)) is not None:
            return avatar_url
        # inclusions
        for search_name, candidate in self.INCLUSIVE_AVATAR_MAPPING.items():
            if username.startswith(search_name):
                return candidate
        # else
        return MISSING

    async def send_log_record(self, record: Record) -> None:
        """Send Log record to discord webhook as a plain message."""
        emoji = record["level"].icon or "\N{WHITE QUESTION MARK ORNAMENT}"  # icons are set in `logs.LEVELS`
        text = f"{emoji} {discord.utils.format_dt(record['time'], style='T')} {record['message']}"
        content = text if len(text) <= 2000 else text[:1999] + "…"
        name = record["name"] or "unknown"
        await self.logger_webhook.send(
            content=content,
            username=name.replace("discord", "dpy")[:80],  # Discord disallows usernames containing "discord"
            avatar_url=self.get_avatar(name),
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
                logger.debug("Waiting {:.2f} seconds to send the record.", total_seconds)
                await asyncio.sleep(total_seconds)

            self._most_recent = clock.utcnow()
            try:
                await self.send_log_record(record)
            except Exception:  # ruff: ignore[blind-except]
                traceback.print_exc()
