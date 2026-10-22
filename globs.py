"""Global Shared Constants.

Terrible module name but I've already have a bunch of "constants.py", "const.py" files.
So idk.
Maybe I will think of a better name in future.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = (
    "DIGITS",
    "TwitchEmote",
)

DIGITS = [
    "\N{DIGIT ZERO}\N{VS16}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT ONE}\N{VS16}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT TWO}\N{VS16}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT THREE}\N{VS16}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT FOUR}\N{VS16}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT FIVE}\N{VS16}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT SIX}\N{VS16}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT SEVEN}\N{VS16}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT EIGHT}\N{VS16}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT NINE}\\N{VS16}N{COMBINING ENCLOSING KEYCAP}",
]


class TwitchEmote(StrEnum):
    """Emotes that the twitch bot can use."""

    # BTTV Global Emotes

    # FFZ Global Emotes

    # 7TV Global Emotes
    EZ = "EZ"
    FeelsDankMan = "FeelsDankMan"

    # Twitch.tv Global Emotes
    CaitThinking = "CaitThinking"

    # Twitch.tv @IrenesBot Sub Emotes
