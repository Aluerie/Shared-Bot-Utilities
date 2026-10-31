# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Discord.py."""

from typing import TYPE_CHECKING, NotRequired, TypedDict

if TYPE_CHECKING:
    import discord


class SendKwargs(TypedDict):
    """Keyword arguments for ``.send`` and ``send``-like methods.

    These should be applicable to all ways to send a message:

    * Context (ctx);
    * Channel (and any other Messageable);
    * Interaction;
    * Webhook;
    * Etc.
    """

    content: NotRequired[str]
    embed: NotRequired[discord.Embed]
    file: NotRequired[discord.File]
    allowed_mentions: NotRequired[discord.AllowedMentions]
    view: NotRequired[discord.ui.View]


class InteractionSendKwargs(SendKwargs):
    """Same as `SendKwargs`, but for interaction responses which also support ``ephemeral``."""

    ephemeral: NotRequired[bool]
