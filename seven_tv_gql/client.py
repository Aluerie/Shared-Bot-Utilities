"""
Seven TV Client.

License
-------
* License: MPL-2.0, see LICENSE for more details.
* Copyright: (C) 2020-present @Aluerie.
"""

from __future__ import annotations

# import asyncio
import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any

import orjson
from aiohttp import ClientSession

from shared import errors, fmt

from .constants import EMOTE, STV_REQUEST_TIMEOUT
from .exceptions import InvokeQueryError
from .models import Emote, PartialEmote, PartialEmoteSet, PartialUser

if TYPE_CHECKING:
    from collections.abc import Mapping

    from shared.types_.database import PoolTypedWithAny

    from ..types_ import seven_tv as stv_types


__all__ = ("GraphQL7TVClient",)

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class GraphQL7TVClient:
    """Seven TV GraphQL API Wrapper.

    This class offers a few methods to perform some common operations with 7TV.
    Such as add, remove, find emote and many more.
    This class uses V4 GQL Endpoint: https://api.7tv.app/v4/gql

    Most of operations here rely on @IrenesBot's 7TV account as they are performed with its Bearer Token.

    Links
    -----
    * https://7tv.app/api/docs
        7TV API Docs
    * https://7tv.io/v4/gql/playground
        7TV GraphQL playground.
    * https://github.com/SevenTV/SevenTV/issues/216
        Remember to search in their issues for some examples of GraphQL requests/responses.

    Parameters
    ----------
    token: str
        Bearer Token for Seven TV API usage.
    session: ClientSession | None = None
        If provided, then the wrapper will use it as its session calls.
        Otherwise, it will create a new `ClientSession` on every API call.
    """

    def __init__(
        self,
        *,
        pool: PoolTypedWithAny,
        bot_7tv_user_id: str,
        bearer_token: str | None = None,
    ) -> None:
        self._bearer_token = bearer_token
        self.user_id: str = bot_7tv_user_id
        self.session = ClientSession()
        self.pool = pool

    async def invoke(self, query: str, variables: Mapping[str, Any]) -> Any:
        """Invoke a request to 7TV GraphQL API.

        Parameters
        ----------
        query: str
            GraphQL query.
        variables: Mapping[str, Any]
            (Mapping[str, Any] is type-hinting crunch to be compatible with TypedDict, this is supposed to be dict[str, Any])
            Dictionary of variables to be provided with query into `json` kwarg of GraphQL request.

        Returns
        -------
        dict[str, Any]
            GraphQL json dictionary from the response. Usually heavily nested.

        Raises
        ------
        GraphQLResponseError
            If API json response contains `errors` field then `GraphQLResponseError` is raised with its content.
        """
        match = re.search(r"^\s*(?:query|mutation)\s+(?P<query_name>\w+)\s*(?:\(|\{)", query)
        log.debug("7TV GraphQL - invoking query %s", match.group("query_name") if match else "UnknownQuery")

        try:
            async with (
                asyncio.timeout(STV_REQUEST_TIMEOUT),
                (self.session).post(
                    url="https://api.7tv.app/v4/gql",
                    json={"query": query, "variables": variables},
                    headers={"Authorization": self._bearer_token} if self._bearer_token else None,
                ) as response,
            ):
                if response.ok:
                    gql_json = await response.json(loads=orjson.loads)
                else:
                    msg = f"7TV is unavailable/lagging/down {EMOTE}"
                    for_devs = f"7TV was not ok. Status: {response.status}\nText:\n{fmt.codeblock(await response.text())}"
                    raise errors.RespondAndNotifyDevsError(msg, for_devs) from None

        except TimeoutError:
            msg = f"7TV didn't respond to me in time; try again later? {EMOTE}"
            raise errors.RespondWithError(msg) from None

        match gql_json:
            case {"data": data} if data:
                return data
            case {"errors": gql_errors} if gql_errors:
                error = gql_errors[0]
                # This way we are only raising error corresponding to the first error in the gql_json
                # but we are okay with that, I think.
                extensions = error.get("extensions", {})
                raise InvokeQueryError(
                    status=extensions.get("status", "???"),
                    message=error.get("message", ""),
                    code=extensions.get("code", "UNKNOWN_CODE"),
                )
            case {"status": status} if status == "Unauthorized":
                # If bearer token expired -
                # 7TV sends {'status': 'Unauthorized', 'error_code': 1000, 'error': 'invalid session'}
                msg = (
                    "I am not unauthorized to do this - 7TV logged me out; Irene will fix it (surely permanently this time)"
                )
                for_devs = "The bot's 7TV Bearer Token is expired."
                raise errors.RespondAndNotifyDevsError(msg, for_devs, gql_json=gql_json)
            case _:
                msg = "Something went wrong"
                raise errors.SomethingWentWrongError(msg, data=gql_json)

    def create_partial_emote(self, emote_id: str) -> PartialEmote:
        """Create partial emote."""
        return PartialEmote(self, emote_id)

    def create_partial_emote_set(self, emote_set_id: str) -> PartialEmoteSet:
        """Create partial emote set."""
        return PartialEmoteSet(self, emote_set_id)

    def create_partial_user(self, twitch_id: str) -> PartialUser:
        """Create partial user."""
        return PartialUser(self, twitch_id)

    async def search_emote(self, emote_name: str, index: int = 0) -> PartialEmote:
        """Search Emote by name."""
        query = """
query TopSearchByEmoteName($emoteName: String) {
  emotes {
    search(
      query: $emoteName
      sort: {sortBy: TOP_ALL_TIME, order: DESCENDING}
      filters: {exactMatch: true}
    ) {
      items {
        id
        defaultName
      }
    }
  }
}
        """
        variables = {"emoteName": emote_name}
        res: stv_types.TopSearchByEmoteName = await self.invoke(query, variables)
        # For some reason "exactMatch": true filter still allows difference capitalizations so we still have to `==`.
        emote_items = sorted(
            res["emotes"]["search"]["items"],
            key=lambda item: item["defaultName"] == emote_name,
            reverse=True,
        )
        try:
            return PartialEmote(self, emote_id=emote_items[index]["id"])
        except IndexError:
            msg = f"Result search doesn't have that many emotes (only one {len(res)})"
            raise errors.RespondWithError(msg) from None

    async def fetch_emote(self, emote_id: str) -> Emote:
        """
        Get defaultName for an emote.

        Parameters
        ----------
        emote_id: str
            7TV emote id.

        Returns
        -------
        Emote
            Seven TV Emote.
        """
        return await PartialEmote(self, emote_id).fetch()
