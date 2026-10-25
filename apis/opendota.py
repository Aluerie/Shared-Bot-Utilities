"""Opendota API Wrapper.

Links
-----
* https://docs.opendota.com/
* https://www.opendota.com/
* https://github.com/odota


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

    from shared.typings import opendota as schemas


__all__ = ("OpenDotaClient",)
log = logging.getLogger(__name__)


class Match:
    def __init__(self, data: schemas.Matches) -> None:
        self.id = data["match_id"]
        self.players = [MatchPlayer(p) for p in data["players"]]


class MatchPlayer:
    def __init__(self, data: schemas.MatchesPlayer) -> None:
        try:
            id_ = data["account_id"]
        except KeyError:
            # If person has expose data off - their ID just not included in the response
            id_ = None
        self.id: int | None = id_


class OpenDotaClient:
    """A class for interacting with OpenDota API."""

    def __init__(self, *, session: aiohttp.ClientSession) -> None:
        self.session = session

    async def _invoke(self, endpoint: str) -> Any:
        """Invoke a request to OpenDota API."""
        url = f"https://api.opendota.com/api/{endpoint}"
        async with self.session.get(url=url) as resp:
            return await resp.json(loads=orjson.loads)

    async def matches(self, match_id: int) -> Match:
        """Get match from opendota API via GET matches endpoint."""
        data: schemas.Matches = await self._invoke(f"matches/{match_id}")
        return Match(data)

    async def get_items(self) -> schemas.ItemsQuery:
        """Get Opendota constants items.

        Links
        -----
        * https://api.opendota.com/api/constants/items
        * https://raw.githubusercontent.com/odota/dotaconstants/master/build/items.json
        """
        log.debug("🍋 Opendota Constants API: getting items.")
        return await self._invoke("constants/items")
