"""Bot Base.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

import logging
from pathlib import Path
from pkgutil import iter_modules
from typing import TYPE_CHECKING, Any

import discord

from shared import fmt

from .error_notifications import ErrorNotificationManager

if TYPE_CHECKING:
    import aiohttp

try:
    from subset import SUBSET  # ty: ignore[unresolved-import, unused-ignore-comment, unused-ignore-comment]
except ModuleNotFoundError:
    SUBSET: dict[str, list[str]] = {}


__all__ = ("BotBase",)


log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


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
    def add_codeblock_field(
        embed: discord.Embed,
        *,
        data: dict[str, Any],
        field_name: str = "Extra Data",
    ) -> discord.Embed:
        """Add data to an embed as nicely formatted field."""
        embed.add_field(name=field_name, value=fmt.pformat_dict(data), inline=False)
        return embed

    def get_extensions(
        self,
        *,
        is_subset_mode: bool,
        package: str,
        disabled_extensions: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Get list of bot extensions to load.

        Discord.py uses term 'extensions' so I will use it too, however keep in mind that some libraries
        prefer other words, e.g. twitchIO calls it 'modules'.

        I keep those extensions in `ext` folder.

        Returns
        -------
        tuple[str, ...]
            Tuple of extensions for the bot to load.
            The extensions are given in a full dot form.
            Example: `('ext.personal.alerts', 'ext.dev.control', 'ext.public.dota_rp_flow', )`
        """
        if is_subset_mode:
            # We only need modules from SUBSET
            # Also load `ext.beta`
            return (
                *tuple(
                    f"ext.{category}.{extension}"
                    for category, extensions in SUBSET.items()
                    for extension in extensions
                    if extensions
                ),
                "ext.beta",
            )

        # assume running full bot functionality (besides `DISABLED_MODULES`)
        current_folder = f"src/{package}"
        extensions: tuple[str, ...] = ()
        ext_categories = [path for path in Path(current_folder).iterdir() if path.is_dir() and not path.name.startswith("_")]
        for ext_category in ext_categories:
            # Personal and Public modules
            extensions += tuple(
                extension.name
                for extension in iter_modules([ext_category.absolute()], prefix=f"{package}.{ext_category.name}.")
                if extension.name not in disabled_extensions
            )

        log.debug("The list of modules (%s total) to load: %s", len(extensions), extensions)
        return extensions
