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

import datetime as dt
import itertools
import logging
from typing import TYPE_CHECKING, Any

import orjson
from steam.ext.dota2 import GameMode, Hero, LobbyType

from shared import errors

if TYPE_CHECKING:
    from aiohttp import ClientSession

    from shared.types_ import dota2com as schemas


__all__ = ("Dota2comClient",)

log = logging.getLogger(__name__)


class HeroListHero:
    def __init__(self, data: schemas.HeroListHero) -> None:
        self.id: int = data["id"]
        self.display_name: str = data["name_english_loc"]
        self.npc_name: str = data["name"]


class RealTimeStats:
    def __init__(self, data: schemas.RealTimeStats) -> None:
        self.id = int(data["match"]["match_id"])
        self.lobby_type: LobbyType = LobbyType.try_value(data["match"]["lobby_type"])
        self.game_mode: GameMode = GameMode.try_value(data["match"]["game_mode"])
        self.started_at: dt.datetime = dt.datetime.fromtimestamp(data["match"]["start_timestamp"], tz=dt.UTC)
        self.players: list[RealTimeStatsPlayer] = [
            RealTimeStatsPlayer(p) for p in itertools.chain(data["teams"][0]["players"], data["teams"][1]["players"])
        ]
        self.radiant_nw: int = data["teams"][0]["net_worth"]
        self.radiant_score: int = data["teams"][0]["score"]
        self.dire_nw: int = data["teams"][1]["net_worth"]
        self.dire_score: int = data["teams"][1]["score"]


class RealTimeStatsPlayer:
    def __init__(self, data: schemas.RealTimeStatsTeamPlayer) -> None:
        self.id: int = data["accountid"]
        self.name: str = data["name"]
        self.hero: Hero = Hero.try_value(data["heroid"])
        self.level: int = data["level"]
        self.kills: int = data["kill_count"]
        self.assists: int = data["assists_count"]
        self.deaths: int = data["death_count"]
        self.creep_score: int = data["lh_count"]
        self.denies: int = data["denies_count"]
        self.networth: int = data["net_worth"]
        self.items: list[int] = data.get("items", [])


class Dota2comClient:
    """A class for interacting with Dota 2 Datafeed API."""

    def __init__(self, *, session: ClientSession) -> None:
        self.session: ClientSession = session

    async def _invoke(self, endpoint: str, **query_kwargs: Any) -> Any:
        """Invoke a request to OpenDota API."""
        async with self.session.get(
            url=f"https://www.dota2.com/{endpoint}",
            params=query_kwargs,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"},
        ) as resp:
            return await resp.json(loads=orjson.loads)

    async def hero_list(self, language: str = "english") -> list[HeroListHero]:
        """Get hero list.

        References
        ----------
        * https://www.dota2.com/datafeed/herolist?language=english
        """
        data: list[schemas.HeroListHero] = await self._invoke("datafeed/herolist", language=language)
        return [HeroListHero(d) for d in data]

    async def real_time_stats(self, server_steam_id: int | None) -> RealTimeStats:
        """Get real time stats.

        References
        ----------
        * https://dota2.com/webapi/IDOTA2MatchStats/GetRealtimeStats/v001?server_steam_id=90295464167395331
        """
        if server_steam_id is None:
            msg = "This match does not support real time stats"
            raise errors.RespondWithError(msg)

        data: schemas.RealTimeStats | None = await self._invoke(
            endpoint="webapi/IDOTA2MatchStats/GetRealtimeStats/v001",
            server_steam_id=server_steam_id,
        )
        if not data:
            msg = "It seems this match is not live, no stats were received"
            raise errors.RespondWithError(msg)
        return RealTimeStats(data)

    # Other links that can be interesting (maybe implement in future):
    # * Patch Notes - https://www.dota2.com/datafeed/patchnotes?version=7.41f&language=english
    # * Patch Notes List - https://www.dota2.com/datafeed/patchnoteslist
    # * Ability - https://www.dota2.com/datafeed/abilitydata?language=english&ability_id=5586
    # * Ability List - https://www.dota2.com/datafeed/abilitylist?language=english
    # * Hero Data - https://www.dota2.com/datafeed/herodata?language=english&hero_id=1
    # * Item - https://www.dota2.com/datafeed/itemdata?language=english&item_id=600
    # * Item List - https://www.dota2.com/datafeed/itemlist?language=english
    # * Leaderboards - https://www.dota2.com/webapi/ILeaderboard/GetDivisionLeaderboard//v0001?division=europe&leaderboard=0
    # * League Info List - https://www.dota2.com/webapi/IDOTA2League/GetLeagueInfoList/v001
