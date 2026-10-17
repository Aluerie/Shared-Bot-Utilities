"""Bot Base.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord

from shared import fmt

from .error_notifications import ErrorNotificationManager

if TYPE_CHECKING:
    import aiohttp


class BotBase:
    """Bot Base."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        ping_role_mention: str,
        error_webhook_url: str,
        notification_webhook_url: str,
    ) -> None:
        self.session: aiohttp.ClientSession = session
        self.ping_role_mention: str = ping_role_mention
        self._notification_webhook_url: str = notification_webhook_url

        self.error_notification_manager = ErrorNotificationManager(self, error_webhook_url)

    def webhook_from_url(self, url: str) -> discord.Webhook:
        """Shortcut to discord.Webhook.from_url with some filled args."""
        return discord.Webhook.from_url(url=url, session=self.session)

    @discord.utils.cached_property
    def notification_webhook(self) -> discord.Webhook:
        """Webhook in hideout server to send notifications to the developer(-s)."""
        return self.webhook_from_url(self._notification_webhook_url)

    async def notify_developers(self, content: str = "", **send_kwargs: Any) -> None:
        """Notify developers.

        Parameters
        ----------
        content: str
            Content to send together with the error-role ping.
        send_kwargs: Any
            Kwargs for `webhook.send` method. Look for supported argument in `discord.Webhook.send` method.
        """
        content = f"{self.ping_role_mention}\n{content}"
        await self.notification_webhook.send(content, **send_kwargs)

    @staticmethod
    def add_codeblock_field(embed: discord.Embed, *, data: dict[str, Any], field_name: str = "Extra Data") -> discord.Embed:
        """Add data to an embed as nicely formatted field."""
        embed.add_field(name=field_name, value=fmt.pformat_dict(data), inline=False)
        return embed
