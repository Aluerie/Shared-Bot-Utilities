# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Dota 2 Datafeed API Wrapper.

This API is not public per se.
Just looked up some calls in Network tab.

Links
-----
* https://www.dota2.com/
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, override
from warnings import deprecated

import aiohttp
import orjson

from shared import errors, globs

# The real time stats are the same data as in Steam Web API, so the classes are shared (and re-exported).
from shared.apis.steam_web import RealTimeStats, RealTimeStatsPlayer

if TYPE_CHECKING:
    from shared.typings import dota2com as schemas


__all__ = (
    "Dota2comClient",
    "HeroListHero",
    "ItemListItem",
    "RealTimeStats",
    "RealTimeStatsPlayer",
)

log = logging.getLogger(__name__)

BASE_URL = "https://www.dota2.com"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)  # seconds, aiohttp's default is 5 minutes


class HeroListHero:
    """A hero from the hero list.

    Attributes
    ----------
    id
        The hero ID.
    display_name
        The English display name of the hero.
    npc_name
        The internal name of the hero, e.g. ``npc_dota_hero_antimage``.
    """

    def __init__(self, data: schemas.HeroListHero) -> None:
        self.id: int = data["id"]
        self.display_name: str = data["name_english_loc"]
        self.npc_name: str = data["name"]

    @override
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} display_name={self.display_name!r}>"


class ItemListItem:
    """An item from the item list.

    Attributes
    ----------
    id
        The item ID.
    display_name
        The English display name of the item.
    """

    def __init__(self, data: schemas.ItemListItem) -> None:
        self.id: int = data["id"]
        self.display_name: str = data["name_english_loc"]

    @override
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} display_name={self.display_name!r}>"


class Dota2comClient:
    """A client for the Dota 2 Datafeed API.

    Parameters
    ----------
    session
        The session used to make requests. The client does not own it, so the caller is responsible for closing it.

    Attributes
    ----------
    MAX_RETRY_ATTEMPTS
        Amount of attempts before a request is considered failed.
    SLEEP_BETWEEN_ATTEMPTS
        Seconds to wait after the first failed attempt. The wait doubles after each following failure.
    """

    MAX_RETRY_ATTEMPTS = 5
    SLEEP_BETWEEN_ATTEMPTS = 1.0

    def __init__(self, *, session: aiohttp.ClientSession) -> None:
        self.session: aiohttp.ClientSession = session

    async def _invoke(self, endpoint: str, **query_kwargs: Any) -> Any:
        """Make a single GET request to Dota2com webapi/datafeed.

        Parameters
        ----------
        endpoint
            Path relative to ``https://www.dota2.com/``, e.g. ``"datafeed/herolist"``.
        **query_kwargs
            Query parameters for the request.

        Returns
        -------
        Any
            The ``result.data`` part of the decoded JSON body.

        Raises
        ------
        errors.ResponseNotOkError
            If the response status is not 2xx.
        errors.EmptyResponseError
            If the response has no ``result.data``. The web API does that for matches that are not live.
        """
        async with self.session.get(
            url=f"{BASE_URL}/{endpoint}",
            params=query_kwargs,
            headers={"User-Agent": globs.USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            url = str(resp.url.with_query(None))
            if not resp.ok:
                raise errors.ResponseNotOkError(url)
            # the server is not picky about its content type, so don't be either
            payload = await resp.json(loads=orjson.loads, content_type=None)

        data = payload.get("result", {}).get("data") if isinstance(payload, dict) else None
        if not data:
            raise errors.EmptyResponseError(url)
        return data

    async def _get_json(self, endpoint: str, **query_kwargs: Any) -> Any:
        """Make a request to Dota2com webapi/datafeed, retrying on transient failures.

        Retries on non-OK statuses, empty responses, malformed bodies, network errors and timeouts.
        The waits between attempts grow exponentially: 1, 2, 4 and 8 seconds with the default settings.

        Parameters
        ----------
        endpoint
            Path relative to ``https://www.dota2.com/``.
        **query_kwargs
            Query parameters for the request.

        Returns
        -------
        Any
            The ``result.data`` part of the first successful response.

        Raises
        ------
        errors.TooManyFailsError
            If every attempt failed. The last underlying exception is chained as the cause.
        """
        last_exc: Exception | None = None
        for attempt in range(self.MAX_RETRY_ATTEMPTS):
            try:
                return await self._invoke(endpoint, **query_kwargs)
            except (
                errors.ResponseNotOkError,
                errors.EmptyResponseError,
                aiohttp.ClientError,
                TimeoutError,
                ValueError,  # orjson.JSONDecodeError
            ) as exc:
                last_exc = exc
                log.debug("Dota2com %r attempt %d/%d failed: %r", endpoint, attempt + 1, self.MAX_RETRY_ATTEMPTS, exc)
                if attempt < self.MAX_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(self.SLEEP_BETWEEN_ATTEMPTS * 2**attempt)

        msg = f"Dota2com kept failing for endpoint {endpoint!r} with {query_kwargs}."
        raise errors.TooManyFailsError(msg) from last_exc

    async def hero_list(self, language: str = "english") -> list[HeroListHero]:
        """Get hero list.

        Parameters
        ----------
        language
            Language of the localized names.

        References
        ----------
        * https://www.dota2.com/datafeed/herolist?language=english
        """
        data = await self._get_json("datafeed/herolist", language=language)
        heroes: list[schemas.HeroListHero] = data["heroes"]
        return [HeroListHero(d) for d in heroes]

    @deprecated("Use steam_web.py's get_real_time_stats instead")
    async def real_time_stats(self, server_steam_id: int | None) -> RealTimeStats:
        """Get real time stats.

        .. warning::

            This seems to perform worse than steam web API version. Starting from an incognito tab - it often takes 5-6
            page reloads for dota2.com's web-api to respond while steam web API is 1-2 tries, on average.

        Parameters
        ----------
        server_steam_id
            Steam ID of the game server hosting the match.

        References
        ----------
        * https://dota2.com/webapi/IDOTA2MatchStats/GetRealtimeStats/v001?server_steam_id=90295464167395331
        * https://steamapi.xpaw.me/#IDOTA2MatchStats_570/GetRealtimeStats
        """
        if server_steam_id is None:
            msg = "This match does not support real time stats"
            raise errors.UnsupportedError(msg)

        try:
            data: schemas.RealTimeStats = await self._get_json(
                "webapi/IDOTA2MatchStats/GetRealtimeStats/v001", server_steam_id=server_steam_id
            )
        except errors.TooManyFailsError as exc:
            msg = "It seems this match is not live, no stats were received"
            raise errors.RespondWithError(msg) from exc
        return RealTimeStats(data)

    async def item_list(self, language: str = "english") -> list[ItemListItem]:
        """Get item list.

        Parameters
        ----------
        language
            Language of the localized names.

        References
        ----------
        * https://www.dota2.com/datafeed/itemlist?language=english
        """
        data = await self._get_json("datafeed/itemlist", language=language)
        item_abilities: list[schemas.ItemListItem] = data["itemabilities"]
        return [ItemListItem(d) for d in item_abilities]

    # Other links that can be interesting (maybe implement in future):
    # * Patch Notes - https://www.dota2.com/datafeed/patchnotes?version=7.41f&language=english
    # * Patch Notes List - https://www.dota2.com/datafeed/patchnoteslist
    # * Ability - https://www.dota2.com/datafeed/abilitydata?language=english&ability_id=5586
    # * Ability List - https://www.dota2.com/datafeed/abilitylist?language=english
    # * Hero Data - https://www.dota2.com/datafeed/herodata?language=english&hero_id=1
    # * Item - https://www.dota2.com/datafeed/itemdata?language=english&item_id=600
    # * Leaderboards - https://www.dota2.com/webapi/ILeaderboard/GetDivisionLeaderboard//v0001?division=europe&leaderboard=0
    # * League Info List - https://www.dota2.com/webapi/IDOTA2League/GetLeagueInfoList/v001
