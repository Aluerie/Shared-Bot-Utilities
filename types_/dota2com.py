"""Dota 2 Datafeed.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ("HeroListHero",)


class HeroListHero(TypedDict):
    """https://www.dota2.com/datafeed/herolist?language=english."""

    id: int
    name: str
    name_loc: str
    name_english_loc: str
    primary_attr: int
    complexity: int
