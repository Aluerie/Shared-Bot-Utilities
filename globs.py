"""
Global Shared Constants.

Terrible module name but I've already have a bunch of "constants.py", "const.py" files.
So idk.
Maybe I will think of a better name in future.

License
-------
* License: MPL-2.0, see LICENSE for more details.
* Copyright: (C) 2020-present @Aluerie.
"""

from enum import StrEnum

__all__ = (
    "DIGITS",
    "Global7TV",
)

DIGITS = [
    "\N{DIGIT ZERO}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT ONE}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT TWO}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT THREE}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT FOUR}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT FIVE}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT SIX}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT SEVEN}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT EIGHT}\N{COMBINING ENCLOSING KEYCAP}",
    "\N{DIGIT NINE}\N{COMBINING ENCLOSING KEYCAP}",
]


class Global7TV(StrEnum):
    """Global 7TV Emotes."""

    EZ = "EZ"
    FeelsDankMan = "FeelsDankMan"


class Irene(StrEnum):
    """Some often used 7TV snowflakes."""

    stv_emote_set_id = "01FAQVCS500002EV4FV330P46A"
    stv_user_id = "01FAQVCS500002EV4FV330P46A"
    twitch_id = "180499648"


class IrenesBot(StrEnum):
    """Some often used 7TV snowflakes."""

    stv_emote_set_id = "01FAQVCS500002EV4FV330P46A"
    stv_user_id = "01KFF67D46PJPD1S6DPFFT06E3"
