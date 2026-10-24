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
from typing import TYPE_CHECKING, Any

import aiohttp
import orjson
from steam.ext.dota2 import GameMode, Hero, LobbyType

from shared import errors, globs

if TYPE_CHECKING:
    from shared.types_ import steam_web as schemas


__all__ = (
    "RealTimeStats",
    "RealTimeStatsPlayer",
    "SteamWebAPIClient",
)
log = logging.getLogger(__name__)


class RealTimeStatsPlayer:
    """A player's live stats within an in-progress Dota 2 match.

    Attributes
    ----------
    id: int
        The player's Steam account ID.
    name: str
        The player's current display name.
    hero: Hero
        The hero the player is playing.
    level: int
        The hero's current level.
    kills: int
        Number of kills.
    assists: int
        Number of assists.
    deaths: int
        Number of deaths.
    creep_score: int
        Number of last hits.
    denies: int
        Number of denied creeps.
    networth: int
        The player's current net worth in gold.
    items: list[int]
        IDs of the items in the player's inventory. Empty if the API omits them.
    """

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


class RealTimeStats:
    """A snapshot of an in-progress Dota 2 match, as returned by ``GetRealtimeStats``.

    Attributes
    ----------
    id: int
        The match ID.
    lobby_type: LobbyType
        The lobby type of the match.
    game_mode: GameMode
        The game mode of the match.
    started_at: datetime.datetime
        When the match started, as a timezone-aware UTC datetime.
    players: list[RealTimeStatsPlayer]
        All players in the match, Radiant first, then Dire.
    radiant_nw: int
        Radiant's total net worth in gold.
    radiant_score: int
        Radiant's kill score.
    dire_nw: int
        Dire's total net worth in gold.
    dire_score: int
        Dire's kill score.
    """

    def __init__(self, data: schemas.RealTimeStats) -> None:
        self.id: int = int(data["match"]["match_id"])
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


class SteamWebAPIClient:
    """A client for the Steam Web API.

    Parameters
    ----------
    api_key: str
        Steam Web API key. It is sent with every request.
    session: aiohttp.ClientSession
        The session used to make requests. The client does not own it, so the caller is responsible for closing it.
    """

    MAX_RETRY_ATTEMPTS = 10
    SLEEP_BETWEEN_ATTEMPTS = 0.5

    def __init__(self, *, api_key: str, session: aiohttp.ClientSession) -> None:
        self.session: aiohttp.ClientSession = session
        self.api_key: str = api_key

    async def _invoke(self, endpoint: str, **query_kwargs: Any) -> Any:
        """Make a single GET request to the Steam Web API.

        Parameters
        ----------
        endpoint: str
            Path relative to ``https://api.steampowered.com/``, e.g. ``"IDOTA2MatchStats_570/GetRealtimeStats/v1"``.
        **query_kwargs
            Query parameters for the request. The API key is added automatically.

        Returns
        -------
        Any
            The decoded JSON body.

        Raises
        ------
        errors.ResponseNotOkError
            If the response status is not 2xx.
        errors.EmptyResponseError
            If the response body is empty. Valve often returns ``{}`` on the first request for a match.

        Notes
        -----
        The API key is stripped from the URL in raised errors so it doesn't leak into logs.
        """
        async with self.session.get(
            url=f"https://api.steampowered.com/{endpoint}",
            params={"key": self.api_key, **query_kwargs},
            headers={"User-Agent": globs.USER_AGENT},
        ) as resp:
            if resp.ok:
                data = await resp.json(loads=orjson.loads)
                if not data:
                    raise errors.EmptyResponseError(str(resp.url.with_query(None)))
                return data
            raise errors.ResponseNotOkError(str(resp.url.with_query(None)))

    async def _get_json(self, endpoint: str, **query_kwargs: Any) -> Any:
        """Make a request to the Steam Web API, retrying on transient failures.

        Retries up to 10 times, waiting 0.5 seconds between attempts, on non-OK statuses, empty responses,
        network errors and timeouts.

        Parameters
        ----------
        endpoint: str
            Path relative to ``https://api.steampowered.com/``.
        **query_kwargs
            Query parameters for the request.

        Returns
        -------
        Any
            The decoded JSON body of the first successful response.

        Raises
        ------
        errors.TooManyFailsError
            If every attempt failed. The last underlying exception is chained as the cause.
        """
        last_exc: Exception | None = None
        for attempt in range(self.MAX_RETRY_ATTEMPTS):
            try:
                return await self._invoke(endpoint, **query_kwargs)
            except (errors.ResponseNotOkError, errors.EmptyResponseError, aiohttp.ClientError, TimeoutError) as exc:
                if attempt < self.MAX_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(self.SLEEP_BETWEEN_ATTEMPTS)
                last_exc = exc

        msg = f"Steam Web API kept failing for endpoint {endpoint!r} with {query_kwargs}."
        raise errors.TooManyFailsError(msg) from last_exc

    async def get_real_time_stats(self, server_steam_id: int | None) -> RealTimeStats:
        """Get live stats for an in-progress Dota 2 match.

        Parameters
        ----------
        server_steam_id: int
            Steam ID of the game server hosting the match.

        References
        ----------
        * https://steamapi.xpaw.me/#IDOTA2MatchStats_570/GetRealtimeStats.
        """
        if server_steam_id is None:
            msg = "This match does not support real time stats"
            raise errors.UnsupportedError(msg)

        data: schemas.RealTimeStats = await self._get_json(
            "IDOTA2MatchStats_570/GetRealtimeStats/v1", server_steam_id=server_steam_id
        )
        return RealTimeStats(data)
