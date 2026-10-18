"""Dota 2 Datafeed API Wrapper.

This API is not public per se.
Just looked up some calls in Network tab.

Links
-----
* https://www.dota2.com/


License
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import orjson

if TYPE_CHECKING:
    import aiohttp

    from shared.types_ import dota2com as schemas


__all__ = ("Dota2comClient",)

log = logging.getLogger(__name__)


class HeroListHero:
    def __init__(self, data: schemas.HeroListHero) -> None:
        self.id: int = data["id"]
        self.display_name: str = data["name_english_loc"]
        self.npc_name: str = data["name"]


class Dota2comClient:
    """A class for interacting with Dota 2 Datafeed API."""

    def __init__(self, *, session: aiohttp.ClientSession) -> None:
        self.session = session

    async def _invoke(self, endpoint: str, **query_kwargs: Any) -> Any:
        """Invoke a request to OpenDota API."""
        queries = "&".join(f"{k}={v}" for k, v in query_kwargs.items())
        url = f"https://www.dota2.com/{endpoint}?{queries}"
        async with self.session.get(url=url) as resp:
            return await resp.json(loads=orjson.loads)

    async def hero_list(self, language: str = "english") -> list[HeroListHero]:
        """Get hero list.

        Links
        -----
        * https://www.dota2.com/datafeed/herolist?language=english
        """
        data: list[schemas.HeroListHero] = await self._invoke("datafeed/herolist", language=language)
        return [HeroListHero(d) for d in data]

    async def real_time_stats(self, server_steam_id: int) -> Any:
        """Get real time stats."""
        # Warning - I've had some
        # `aiohttp.client_exceptions.ClientConnectorError: Cannot connect to host www.dota2.com:443 ssl:default
        # [The semaphore timeout period has expired]`
        # So maybe don't use it?
        return await self._invoke("webapi/IDOTA2MatchStats/GetRealtimeStats/v001", server_steam_id=server_steam_id)

    # Other links that can be interesting
    # -----------------------------------
    # * Patch Notes - https://www.dota2.com/datafeed/patchnotes?version=7.41f&language=english
    # * Patch Notes List - https://www.dota2.com/datafeed/patchnoteslist

    # * Ability - https://www.dota2.com/datafeed/abilitydata?language=english&ability_id=5586
    # * Ability List - https://www.dota2.com/datafeed/abilitylist?language=english

    # * Hero Data - https://www.dota2.com/datafeed/herodata?language=english&hero_id=1

    # * Item - https://www.dota2.com/datafeed/itemdata?language=english&item_id=600
    # * Item List - https://www.dota2.com/datafeed/itemlist?language=english

    # * Leaderboards - https://www.dota2.com/webapi/ILeaderboard/GetDivisionLeaderboard//v0001?division=europe&leaderboard=0

    # * https://www.dota2.com/webapi/IDOTA2League/GetLeagueInfoList/v001
