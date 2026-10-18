"""Steam Web API Clients.

License
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import itertools
import logging
from typing import TYPE_CHECKING, Any, TypedDict

import orjson
from steam.ext.dota2 import GameMode, Hero, LobbyType

from shared import errors

if TYPE_CHECKING:
    from aiohttp import ClientSession

    from shared.types_ import steam_web_api as schemas

    class GraphQLData(TypedDict):
        data: Any


__all__ = ("SteamWebAPIClient",)
log = logging.getLogger(__name__)


class RealTimeStats:
    def __init__(self, data: schemas.RealTimeStats) -> None:
        self.id = int(data["match"]["match_id"])
        self.lobby_type: LobbyType = LobbyType.try_value(data["match"]["lobby_type"])
        self.game_mode: GameMode = GameMode.try_value(data["match"]["game_mode"])
        self.started_at: dt.datetime = dt.datetime.fromtimestamp(data["match"]["start_timestamp"], tz=dt.UTC)
        self.players = [
            RealTimeStatsPlayer(p) for p in itertools.chain(data["teams"][0]["players"], data["teams"][1]["players"])
        ]
        self.radiant_nw = data["teams"][0]["net_worth"]
        self.radiant_score: int = data["teams"][0]["score"]
        self.dire_nw: int = data["teams"][1]["net_worth"]
        self.dire_score: int = data["teams"][1]["score"]


class RealTimeStatsPlayer:
    def __init__(self, data: schemas.RealTimeStatsTeamPlayer) -> None:
        self.id = data["accountid"]
        self.name: str = data["name"]
        self.hero: Hero = Hero.try_value(data["heroid"])
        self.level: int = data["level"]
        self.kills = data["kill_count"]
        self.assists = data["assists_count"]
        self.deaths = data["death_count"]
        self.creep_score = data["lh_count"]
        self.denies = data["denies_count"]
        self.networth = data["net_worth"]
        try:
            self.items = data["items"]
        except KeyError:
            self.items = []


class SteamWebAPIClient:
    """A class for interacting with Steam Web API.

    Parameters
    ----------
    api_key: str
        Steam Web API Key. Needed for all requests.

    """

    def __init__(self, *, api_key: str, session: ClientSession) -> None:
        self.session: ClientSession = session
        self.api_key: str = api_key

    async def _invoke(self, endpoint: str, **kwargs: Any) -> Any:
        """Invoke a request to Steam Web API."""
        queries = "&".join(f"{k}={v}" for k, v in kwargs.items())
        url = f"https://api.steampowered.com/{endpoint}/?key={self.api_key}&{queries}"
        max_failures = 10
        for attempt in range(max_failures):
            async with self.session.get(url) as resp:
                # encoding='utf-8' errored out one day, it seems Valve have misconfigured some servers' content types?
                result = await resp.json(loads=orjson.loads)
                if result:
                    break
                # Valve, why does it return an empty dict `{}` on the very first request for every match...
                # It's a problem even in the actual game client.
                # So we have to ask again hence this silly for loop.
                # some lazy exp backoff:
                await asyncio.sleep(0.49 * 1.7**attempt)
                continue
        else:
            msg = f'Response "{url}" was empty {max_failures} times in a row.'
            raise errors.ApiError(msg)

        return result

    async def get_real_time_stats(self, server_steam_id: int) -> RealTimeStats:
        """Get Real Time Stats from Steam Web API.

        Links
        -----
        * https://steamapi.xpaw.me/#IDOTA2MatchStats_570/GetRealtimeStats.
        """
        data: schemas.RealTimeStats = await self._invoke(
            "IDOTA2MatchStats_570/GetRealtimeStats/v1", server_steam_id=server_steam_id
        )
        return RealTimeStats(data)
