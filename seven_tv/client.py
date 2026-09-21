"""
Seven TV Client.

License
-------
* License: MPL-2.0, see LICENSE for more details.
* Copyright: (C) 2020-present @Aluerie.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import orjson
from aiohttp import ClientSession

from .. import errors
from .exceptions import ConflictingEmoteNameError, EmoteNotFoundInSetError
from .models import Emote, PartialEmote, PartialEmoteSet, PartialUser

if TYPE_CHECKING:
    from collections.abc import Mapping


__all__ = ("SevenTVClient",)

BAD_REQUEST_CONFLICTING_NAME_MESSAGE = "BAD_REQUEST this emote has a conflicting name"
BAD_REQUEST_EMOTE_NOT_FOUND_MESSAGE = "BAD_REQUEST emote not found in set"


class SevenTVClient:
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
        token: str,
        *,
        session: ClientSession | None = None,
    ) -> None:
        self.token: str = token
        self.session: ClientSession | None = session

    async def invoke(self, query: str, *, variables: Mapping[str, Any]) -> dict[str, Any]:
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
        async with (self.session or ClientSession()).post(
            url="https://api.7tv.app/v4/gql",
            json={
                "query": query,
                "variables": variables,
            },
            headers={
                "Authorization": self.token,
            },
        ) as response:
            graph_ql_json = await response.json(loads=orjson.loads)

        # ERRORS
        if "errors" in graph_ql_json:
            graph_ql_errors: list[dict[str, Any]] = graph_ql_json["errors"]
            for gql_error in graph_ql_errors:
                message = gql_error.get("message", "")
                status = gql_error.get("extensions", {}).get("status", "")
                error_msg = f"{status} {message}"

                if message == BAD_REQUEST_CONFLICTING_NAME_MESSAGE:
                    raise ConflictingEmoteNameError(error_msg)
                if message == BAD_REQUEST_EMOTE_NOT_FOUND_MESSAGE:
                    raise EmoteNotFoundInSetError(error_msg)

            raise errors.APIDataError(str(graph_ql_json["errors"]), graph_ql_json["errors"])

        # NO ERRORS
        return graph_ql_json

    def create_partial_emote(self, emote_id: str) -> PartialEmote:
        """Create partial emote."""
        return PartialEmote(self, emote_id)

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

    def create_partial_emote_set(self, emote_set_id: str) -> PartialEmoteSet:
        """Create partial emote set."""
        return PartialEmoteSet(self, emote_set_id)

    def create_partial_user(self, twitch_id: str) -> PartialUser:
        """Create partial user."""
        return PartialUser(self, twitch_id)
