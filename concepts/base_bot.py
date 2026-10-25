"""Bot Base.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

import logging
from pkgutil import iter_modules
from typing import TYPE_CHECKING, Any

import discord

from shared import errors

from .error_notifications import ErrorNotificationManager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from types import ModuleType

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

    SOMETHING_WENT_WRONG_MESSAGE = "Something went wrong"

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        dev_ping: str,
        error_webhook_url: str,
        spam_webhook_url: str,
    ) -> None:
        self.session: aiohttp.ClientSession = session
        self.dev_ping: str = dev_ping
        self._spam_webhook_url: str = spam_webhook_url

        self.error_notification_manager = ErrorNotificationManager(self, error_webhook_url)

    def webhook_from_url(self, url: str) -> discord.Webhook:
        """Shortcut to discord.Webhook.from_url with some filled args."""
        return discord.Webhook.from_url(url=url, session=self.session)

    @discord.utils.cached_property
    def spam_webhook(self) -> discord.Webhook:
        """Webhook in hideout server which devoted to the bot.

        Used for
        * error notifications
        * developer notifications
        * miscellaneous messages
        * etc
        """
        return self.webhook_from_url(self._spam_webhook_url)

    async def notify_developers(self, content: str = "", **send_kwargs: Any) -> None:
        """Notify developers.

        Parameters
        ----------
        content: str
            Content to send together with the error-role ping.
        send_kwargs: Any
            Kwargs for `webhook.send` method. Look for supported argument in `discord.Webhook.send` method.
        """
        content = f"{self.dev_ping}\n{content}"
        await self.spam_webhook.send(content, **send_kwargs)

    def get_extensions(
        self,
        *,
        is_subset_mode: bool,
        package: ModuleType,
    ) -> tuple[str, ...]:
        """Get list of bot extensions to load.

        .. note::

            Discord.py uses term 'extensions' so I will use it too, however keep in mind that some libraries
            prefer other words, e.g. twitchIO calls it 'modules'.

        Parameters
        ----------
        is_subset_mode
            If True, return only the extensions listed in `SUBSET`.
        package
            The package that holds the extensions, e.g. the imported `ext` module.

        Returns
        -------
        tuple[str, ...]
            Extensions in full dotted form, e.g. `('ext.alerts', 'ext.control', 'ext.dev')`.
        """
        if is_subset_mode:
            return tuple(f"{package.__name__}.{extension}" for extension in SUBSET)

        return tuple(
            module_info.name
            for module_info in iter_modules(package.__path__, prefix=f"{package.__name__}.")
            if not module_info.name.rpartition(".")[2].startswith("_")
        )

    async def respond_per_policy(
        self,
        error: Exception,
        respond: Callable[[str], Awaitable[object]],
    ) -> bool:
        """Respond to the user according to the error's policy.

        Returns
        -------
        bool
            Whether Irene should be notified.
        """
        if isinstance(error, errors.BotError):
            policy = error.policy
            response = self.SOMETHING_WENT_WRONG_MESSAGE if error.use_fallback_response else error.response
        else:
            policy = errors.RESPOND_NOTIFY
            response = self.SOMETHING_WENT_WRONG_MESSAGE

        if policy.respond:
            try:
                await respond(response)
            except Exception:
                log.warning("Failed to respond to the user", exc_info=True)
        return policy.notify
