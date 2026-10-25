"""DPY.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from typing import TYPE_CHECKING, NotRequired, TypedDict

if TYPE_CHECKING:
    import discord


class SendKwargs(TypedDict):
    """SendKwargs."""

    content: NotRequired[str]
    embed: NotRequired[discord.Embed]
    file: NotRequired[discord.File]
    allowed_mentions: NotRequired[discord.AllowedMentions]
    view: NotRequired[discord.ui.View]
