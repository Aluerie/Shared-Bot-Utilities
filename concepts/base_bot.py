from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord

if TYPE_CHECKING:
    import aiohttp


class BotBase:
    def __init__(self, session: aiohttp.ClientSession, error_webhook_url: str, error_ping: str) -> None:
        self.session: aiohttp.ClientSession = session
        self._error_webhook_url: str = error_webhook_url
        self.error_ping: str = error_ping

    def webhook_from_url(self, url: str) -> discord.Webhook:
        """Shortcut to discord.Webhook.from_url with some filled args."""
        return discord.Webhook.from_url(url=url, session=self.session)

    @discord.utils.cached_property
    def error_webhook(self) -> discord.Webhook:
        """Webhook in hideout server to send errors/notifications to the developer(-s)."""
        return self.webhook_from_url(self._error_webhook_url)

    async def ping_developers(self, content: str = "", **send_kwargs: Any) -> None:
        """Ping developers.

        Parameters
        ----------
        content: str
            Content to send together with the error-role ping.
        send_kwargs: Any
            Kwargs for `webhook.send` method. Look for supported argument in `discord.Webhook.send` method.
        """
        content = f"{self.error_ping}\n{content}"
        await self.error_webhook.send(content, **send_kwargs)
