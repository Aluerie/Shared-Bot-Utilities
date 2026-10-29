# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Discord.py."""

from typing import TYPE_CHECKING, NotRequired, TypedDict

if TYPE_CHECKING:
    import discord


class SendKwargs(TypedDict):
    """SendKwargs.

    These are used in ``.send`` and ``send``-like methods, e.g. ``interaction.response.send_message``.

    These should be applicable to all ways to send a message:
    * Context (ctx);
    * Channel (and any other Messageable);
    * Interaction;
    * Webhook;
    * Etc.
    """

    content: NotRequired[str]
    embed: NotRequired[discord.Embed]
    embeds: NotRequired[list[discord.Embed]]
    file: NotRequired[discord.File]
    allowed_mentions: NotRequired[discord.AllowedMentions]
    view: NotRequired[discord.ui.View]
    ephemeral: NotRequired[bool]
