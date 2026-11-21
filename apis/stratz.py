# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Stratz API Clients."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict

import aiohttp
import orjson

from shared import errors

if TYPE_CHECKING:
    from aiohttp.client import ClientSession

    from shared.typings import stratz as schemas

    class GraphQLData(TypedDict):
        data: NotRequired[Any]
        errors: NotRequired[list[Any]]


__all__ = ("StratzClient",)
log = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)  # seconds, aiohttp's default is 5 minutes


class StratzClient:
    """A class for interacting with Stratz GraphQL API."""

    def __init__(self, *, bearer_token: str, session: aiohttp.ClientSession) -> None:
        self.session: ClientSession = session
        self.bearer_token: str = bearer_token

    async def _invoke(self, query: str) -> Any:
        """Invoke a request to Stratz GraphQL API."""
        async with self.session.post(
            url="https://api.stratz.com/graphql",
            json={"query": query},
            headers={
                "User-Agent": "STRATZ_API",
                "Authorization": f"Bearer {self.bearer_token}",
                "Content-Type": "application/json",
            },
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            if not resp.ok:
                msg = f"Stratz responded with HTTP {resp.status}"
                raise errors.ResponseNotOkError(msg)
            graphql_json: GraphQLData = await resp.json(loads=orjson.loads)

        # GraphQL sends `"data": null` (or no `data`) together with `errors` when the query fails
        if not (data := graphql_json.get("data")) or bool(graphql_json.get("errors")):
            msg = "Stratz GraphQL API Error"
            raise errors.SomethingWentWrongError(msg, data={"graphql_json": graphql_json})
        return data

    async def get_items(self) -> list[schemas.Item]:
        """Get Constants for Dota 2 Items."""
        log.debug("🍋 Stratz GraphQL API: getting items.")
        query = """
        query AllItemsQuery {
            constants {
                items {
                    id
                    displayName
                }
            }
        }
        """
        data: schemas.ItemData = await self._invoke(query)
        return data["constants"]["items"]
