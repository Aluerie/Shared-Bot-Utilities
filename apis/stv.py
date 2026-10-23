"""7TV API Wrapper.

Some helper methods and classes wrapping:
* GraphQL 7TV API


Just in case, here are some Seven TV Ids so it's less painful to test GraphQL queries:
{
    "emoteSetId": "01FAQVCS500002EV4FV330P46A", # IRENE_EMOTE_SET (BOT_EMOTE_SET too)
    "emoteId": "01GA4TYKW0000EN50T4AGZ0CK8", # 'lebronJAM', not in the set
    "emoteId": "01G5CH6XX80000X2D18ZB9HGA2", # 'yo' emote, in the set
    "userId": "01FAQVCS500002EV4FV330P46A" # IRENE
    "botId": "01KFF67D46PJPD1S6DPFFT06E3" # BOT
}

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, NotRequired, TypedDict, override

import orjson
from aiohttp import ClientSession

from shared import errors

if TYPE_CHECKING:
    from collections.abc import Mapping

    from shared.types_ import seven_tv as stv_types

    class EmotePayload(TypedDict):
        """EmotePayload."""

        id: str
        ownerId: str
        defaultName: str
        flags: EmoteFlagsPayload

    class EmoteFlagsPayload(TypedDict):
        animated: bool

    class EmoteIdWithAlias(TypedDict):
        emoteId: str
        alias: NotRequired[str]

    class AddEmoteVariables(TypedDict):
        emoteSetId: str
        emoteIdWithAlias: EmoteIdWithAlias

    from shared.types_.seven_tv import GetUserEditors, GUEEditors


__all__ = (
    "ConflictingEmoteNameError",
    "Emote",
    "EmoteNotFoundError",
    "EmoteSetEmote",
    "InvalidEmoteAliasError",
    "InvokeQueryError",
    "LackingPrivilegesError",
    "PartialEmote",
    "PartialEmoteSet",
    "PartialUser",
    "ServiceError",
    "StvClient",
    "UnauthorizedError",
    "UnsatisfyingResultError",
)

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


#############################################################################################################################
# CONSTANTS
#############################################################################################################################


STV_REQUEST_TIMEOUT = 20

EMOTE_SET_EMOTES_CAPACITY_LIMIT = 1000


#############################################################################################################################
# EXCEPTIONS
#############################################################################################################################


class SevenTVErrorMixin:
    """Marker mixin for errors related to the 7TV integration.

    This class is to be used for those errors that comes from 7TV API directly, i.e. in `message` field.
    """


class UnauthorizedError(SevenTVErrorMixin, errors.RespondAndNotifyError):
    """Unauthorized."""

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__(
            msg=(
                "It seems bot's 7TV Bearer Token is expired. Irene, please, grab a new one via dev tools or "
                "figure out how to make the bot automatically refresh it."
            ),
            response="Oops, 7TV logged me out; Irene needs to fix it (surely permanently this time)",
            data=data,
        )


class InvokeQueryError(SevenTVErrorMixin, errors.SomethingWentWrongError):
    """InvokeQueryError."""

    def __init__(self, status: Any, message: Any, code: Any) -> None:
        super().__init__(
            msg=f"{status} {message}",
            data={"status": status, "message": message, "code": code},
        )
        self.status = status
        self.message = message
        self.code = code


class UnsatisfyingResultError(SevenTVErrorMixin, errors.RespondWithError):
    """UnsatisfyingResultError."""


class ServiceError(UnsatisfyingResultError):
    """Service Error."""


class EmoteNotFoundError(UnsatisfyingResultError):
    """Emote Not Found In Set Error."""


class ConflictingEmoteNameError(UnsatisfyingResultError):
    """Conflicting Emote Name Error."""


class LackingPrivilegesError(UnsatisfyingResultError):
    """Lacking Privileges Error."""


class InvalidEmoteAliasError(UnsatisfyingResultError):
    """Invalid Emote Alias Error."""


#############################################################################################################################
# MODELS
#############################################################################################################################


COMMON_EMOTE_SUB_QUERY = """
id
ownerId
defaultName
flags {
    animated
}"""


class PartialEmote:
    """Partial Emote."""

    def __init__(self, client: StvClient, emote_id: str) -> None:
        self._client: StvClient = client
        self.id: str = emote_id
        self._animated: bool | None = None

    def url(self, *, no_https: bool = True) -> str:
        """Get URL."""
        prefix = "" if no_https else "https://"
        return f"{prefix}7tv.app/emotes/{self.id}"

    def cdn_url(self, ext: str | None = None) -> str:
        """Get CDN URL.

        Parameters
        ----------
        ext: str | None = None
            .webp .gif .avif .png
        """
        if ext is None:
            mapping = {
                None: "webp",
                True: "gif",
                False: "png",
            }
            ext = mapping[self._animated]
        return f"https://cdn.7tv.app/emote/{self.id}/4x.{ext}"

    async def fetch(self) -> Emote:
        """Fetch 7TV emote."""
        res = await self._client.invoke(
            query="""
            query EmoteFindName($emoteId: Id!) {
                emotes {
                    emote(id: $emoteId) {
                        %s
                    }
                }
            }
            """  # ruff: ignore[printf-string-formatting]
            % (COMMON_EMOTE_SUB_QUERY),
            variables={
                "emoteId": self.id,
            },
        )
        emote: EmotePayload = res["emotes"]["emote"]
        return Emote(self._client, emote)


class Emote(PartialEmote):
    """Emote."""

    def __init__(self, client: StvClient, data: EmotePayload) -> None:
        super().__init__(client, data.get("id"))
        self.owner_id: str = data.get("ownerId")
        self.default_name: str = data.get("defaultName")
        self.animated = self._animated = data["flags"]["animated"]


class EmoteSetEmote:
    """Emote Set Emote."""

    if TYPE_CHECKING:
        id: str
        emote: PartialEmote | Emote
        emote_set: PartialEmoteSet

    def __init__(
        self,
        client: StvClient,
        alias: str,
        emote: str | PartialEmote | Emote,
        emote_set: str | PartialEmoteSet,
    ) -> None:
        self._client = client
        self.alias: str = alias
        if isinstance(emote, str):
            self.id = emote
            self.emote = PartialEmote(client, emote)
        else:
            self.id = emote.id
            self.emote = emote
        if isinstance(emote_set, str):
            self.emote_set = PartialEmoteSet(client, emote_set)
        else:
            self.emote_set = emote_set


class PartialEmoteSet:
    """Partial Emote Set."""

    def __init__(self, client: StvClient, emote_set_id: str) -> None:
        self._client: StvClient = client
        self.id: str = emote_set_id

    @override
    def __repr__(self) -> str:
        return f"<EmoteSet id={self.id}>"

    async def fetch_all_emotes(self) -> list[EmoteSetEmote]:
        """Fetch all emotes in the set."""
        res = await self._client.invoke(
            query="""
query EmotesInSet($id: Id!, $query: String, $page: Int!, $perPage: Int!) {
  emoteSets {
    emoteSet(id: $id) {
      emotes(query: $query, page: $page, perPage: $perPage) {
        items {
          id
          alias
        }
      }
    }
  }
}  """,
            variables={
                "id": self.id,
                # No need to specify $query - that's crazy.
                "page": 1,
                "perPage": EMOTE_SET_EMOTES_CAPACITY_LIMIT,
            },
        )
        return [
            EmoteSetEmote(self._client, item["alias"], item["id"], self)
            for item in res["emoteSets"]["emoteSet"]["emotes"]["items"]
        ]

    async def fetch_emote_alias(self, emote_id: str) -> str:
        """Get emote's alias in the emote alias.

        Parameters
        ----------
        emote_id: str
            7TV emote id.

        Returns
        -------
        str
            Emote's `alias` in the mentioned emote set. If alias wasn't set, it still returns `defaultName`
            for the emote.

        """
        res = await self._client.invoke(
            query="""
query EmoteSetSearchEmoteAlias($emoteSetId: Id!, $emoteId: Id!) {
  emotes {
    emote(id: $emoteId) {
      inEmoteSets(emoteSetIds: [$emoteSetId]) {
        emote {
          alias
        }
      }
    }
  }
}
""",
            variables={"emoteSetId": self.id, "emoteId": emote_id},
        )

        emote: Any | None = res["emotes"]["emote"]["inEmoteSets"][0]["emote"]
        if emote is None:
            msg = f"Could not find {emote_id} in emote set {self.id}"
            raise EmoteNotFoundError(msg)
        return emote["alias"]

    async def remove_emote(self, emote_id: str) -> None:
        """Remove an emote from the emote set.

        Parameters
        ----------
        emote_id: str
            Emote ID of the emote to remove.
        """
        query: str = """
        mutation EmoteSetRemoveEmote($emoteSetId: Id!, $emoteIdWithAlias: EmoteSetEmoteId!) {
            emoteSets {
                emoteSet(id: $emoteSetId) {
                    removeEmote(id: $emoteIdWithAlias) {
                        id
                    }
                }
            }
        }
        """
        variables = {
            "emoteSetId": self.id,
            "emoteIdWithAlias": {
                "emoteId": emote_id,
            },
        }
        try:
            await self._client.invoke(query, variables=variables)
        except InvokeQueryError as error:
            if error.message == "BAD_REQUEST emote not found in set":
                msg = "Emote was not found in set"
                raise EmoteNotFoundError(msg) from None
            raise

    async def add_emote(
        self,
        emote_id: str,
        *,
        emote_alias: str | None = None,
    ) -> None:
        """Add an emote to a 7TV emote set.

        Parameters
        ----------
        emote_id: str
            7TV emote id.
        emote_alias: str | None = None
            If provided then the emote will be added with an alias.
        """
        query = """
mutation EmoteSetAddEmote($emoteSetId: Id!, $emoteIdWithAlias: EmoteSetEmoteId!) {
  emoteSets {
    emoteSet(id: $emoteSetId) {
      addEmote(id: $emoteIdWithAlias) {
        id
      }
    }
  }
}
"""
        variables = {
            "emoteSetId": self.id,
            "emoteIdWithAlias": {"emoteId": emote_id, "alias": emote_alias},
        }
        try:
            await self._client.invoke(query, variables)
        except InvokeQueryError as error:
            match error.message:
                case "BAD_REQUEST this emote has a conflicting name":
                    try:
                        # TODO: Maybe remove this, why do we do an extra request
                        await self.fetch_emote_alias(emote_id)
                    except EmoteNotFoundError:
                        msg = "This emote has a conflicting name"
                        raise ConflictingEmoteNameError(msg) from None
                    else:
                        msg = "This emote is already present in the emote set"
                        raise UnsatisfyingResultError(msg) from None
                case m if "invalid emote alias" in m:
                    msg = "Invalid emote alias"
                    raise InvalidEmoteAliasError(msg) from None
                case "LOAD_ERROR emote set is at capacity":
                    msg = "Emote set is at full capacity"
                    raise UnsatisfyingResultError(msg) from None
                case _:
                    raise

    async def rename_emote(
        self,
        emote_id: str,
        *,
        new_emote_alias: str,
        old_emote_alias: str | None = None,
    ) -> None:
        """Rename 7tv emote."""
        query = """
mutation EmoteSetRenameEmote($emoteSetId: Id!, $emoteIdWithAlias: EmoteSetEmoteId!, $new_name: String!) {
  emoteSets {
    emoteSet(id: $emoteSetId) {
      updateEmoteAlias(id: $emoteIdWithAlias, alias: $new_name) {
        id
      }
    }
  }
}"""
        variables = {
            "emoteSetId": self.id,
            "emoteIdWithAlias": {"emoteId": emote_id, "alias": old_emote_alias},
            "new_name": new_emote_alias,
        }
        try:
            await self._client.invoke(query, variables)
        except InvokeQueryError as error:
            match error.message:
                case "BAD_REQUEST emote name conflict":
                    msg = "Emote name conflict"
                    raise ConflictingEmoteNameError(msg) from None
                case "BAD_REQUEST emote not found in set":
                    msg = "Emote not found in the emote set"
                    raise EmoteNotFoundError(msg) from None
                case m if "invalid emote alias" in m:
                    msg = "Invalid emote alias"
                    raise InvalidEmoteAliasError(msg) from None
                case _:
                    raise

    async def fetch_info(self) -> EmoteSetInfo:
        """Fetch 7TV Emote Set Info."""
        res = await self._client.invoke(
            query="""
query FetchEmoteSetInfo($emoteSetId: Id!) {
  emoteSets {
    emoteSet(id: $emoteSetId) {
      name
      ownerId
    }
  }
}
        """,
            variables={"emoteSetId": self.id},
        )
        emote_set = res["emoteSets"]["emoteSet"]
        return EmoteSetInfo(name=emote_set["name"], owner_id=emote_set["ownerId"])

    async def get_emote_added_by(self, emote_id: str) -> str:
        """Get emote added by."""
        query = """
query GetWhoAdded($emoteSetId: Id!, $emoteId: Id!) {
  emotes {
    emote(id: $emoteId) {
      inEmoteSets(emoteSetIds: [$emoteSetId]) {
        emote {
          addedById
        }
      }
    }
  }
}
"""
        variables = {"emoteSetId": self.id, "emoteId": emote_id}
        res = await self._client.invoke(query, variables)
        try:
            return res["emotes"]["emote"]["inEmoteSets"][0]["emote"]["addedById"]
        except TypeError, KeyError, IndexError:
            # this means res["emotes"]["emote"] is null
            msg = "Emote not found"
            raise EmoteNotFoundError(msg) from None


class PartialUser:
    """Partial Emote Set."""

    def __init__(self, client: StvClient, twitch_id: str) -> None:
        self._client: StvClient = client
        self.twitch_id: str = twitch_id

    async def fetch_active_emote_set(self) -> PartialEmoteSet:
        """Get currently active 7TV emote set for the broadcaster."""
        query = """
        query findActiveEmoteSetByPlatformId ($platformId: String!) {
            users {
                userByConnection(platform: TWITCH, platformId: $platformId ) {
                    style {
                        activeEmoteSetId
                    }
                }
            }
        }
        """
        res = await self._client.invoke(query, variables={"platformId": self.twitch_id})
        return PartialEmoteSet(self._client, res["users"]["userByConnection"]["style"]["activeEmoteSetId"])

    async def search_emote(self, emote_name: str) -> PartialEmote:
        """Search a 7TV emote in a broadcaster's active emote set by emote_name.

        Parameters
        ----------
        emote_name: str
            Emote name to query against.

        Returns
        -------
        PartialEmote
            Emote that matches provided `emote_name` in the broadcaster's active emote set.
        """
        query: str = """
query UserSearchEmote($platformId: String!, $emoteName: String) {
  users {
    userByConnection(platform: TWITCH, platformId: $platformId) {
      style {
        activeEmoteSet {
          emotes(query: $emoteName, page: 1, perPage: 20) {
            items {
              id
              alias
            }
          }
        }
      }
    }
  }
}
        """
        res = await self._client.invoke(
            query,
            variables={
                "emoteName": emote_name,
                "platformId": self.twitch_id,
            },
        )
        candidates = res["users"]["userByConnection"]["style"]["activeEmoteSet"]["emotes"]["items"]
        # `==` - no `.lower()`, no nothing.
        candidate = next((c for c in candidates if c["alias"] == emote_name), None)
        if candidate is None:
            msg = f"Could not find an emote named '{emote_name}' in the streamer emotes; probably invalid emote input"
            raise UnsatisfyingResultError(msg)
        return PartialEmote(self._client, candidate["id"])

    async def check_bot_editor(self) -> EditorCheck:
        """Check bot editor for."""
        res: GetUserEditors = await self._client.invoke(
            query="""
query GetUserEditors($platformId: String!) {
  users {
    userByConnection(platform: TWITCH, platformId: $platformId) {
      editors {
        editorId
        state
        permissions {
          emoteSet {
            manage
          }
        }
      }
    }
  }
}
""",
            variables={"platformId": self.twitch_id},
        )
        try:
            bot_editor = next(
                editor
                for editor in res["users"]["userByConnection"]["editors"]
                if editor["editorId"] == self._client.user_id
            )
        except StopIteration:
            msg = "The bot is yet to receive a 7tv editor request from the streamer"
            raise UnsatisfyingResultError(msg) from None

        return EditorCheck(bot_editor)

    async def fetch_info(self) -> UserInfo:
        """Get Seven TV User ID."""
        res = await self._client.invoke(
            query="""
query GetUserInfo($platformId: String!) {
  users {
    userByConnection(platform: TWITCH, platformId: $platformId) {
      id
      style {
        activeEmoteSet {
          id
          name
        }
      }
    }
  }
}
        """,
            variables={"platformId": self.twitch_id},
        )
        user = res["users"]["userByConnection"]
        return UserInfo(
            id=user["id"],
            active_emote_set_id=user["style"]["activeEmoteSet"]["id"],
            active_emote_set_name=user["style"]["activeEmoteSet"]["name"],
        )

    async def accept_editor(self) -> Literal["ACCEPTED", "REJECTED"]:
        """Accept Editor."""
        user_seven_tv_id = (await self.fetch_info())[0]
        query = """
mutation UpdateEditorState($userId: Id!, $editorId: Id!, $state: UserEditorUpdateState!) {
  userEditors {
    editor(userId: $userId, editorId: $editorId) {
      updateState(state: $state) {
        userId
        editorId
        state
      }
    }
  }
}
        """
        variables = {"editorId": self._client.user_id, "userId": user_seven_tv_id, "state": "ACCEPT"}

        try:
            res = await self._client.invoke(query, variables)
        except InvokeQueryError as error:
            match error.message:
                case "BAD_REQUEST editor is not pending":
                    msg = (
                        "7TV editor request was already accepted"
                        if (await self.check_bot_editor()).state == "ACCEPTED"
                        else "7TV editor request is not pending"
                    )
                    raise UnsatisfyingResultError(msg) from None
                case "LOAD_ERROR user editor not found":
                    msg = "I don't see any 7TV editor requests from this streamer (have you sent it?)"
                    raise UnsatisfyingResultError(msg) from None
                case _:
                    raise

        return res["userEditors"]["editor"]["updateState"]["state"]

    async def get_stv_mods(self) -> list[dict[str, str]]:
        """Get 7TV editors."""
        query = """
query Get7TVMods($platformId: String!) {
  users {
    userByConnection(platform: TWITCH, platformId: $platformId) {
      editors {
        editorId
        state
        editor {
          mainConnection {
            platform
            platformId
            platformDisplayName
          }
        }
      }
    }
  }
}
        """
        variables = {"platformId": self.twitch_id}
        res = await self._client.invoke(query, variables)
        return [editor["editor"]["mainConnection"] for editor in res["users"]["userByConnection"]["editors"]]


class EditorCheck:
    def __init__(self, payload: GUEEditors) -> None:
        self.state = payload.get("state")
        self.permissions = payload.get("permissions")

    @property
    def is_enough_permissions(self) -> bool:
        return self.permissions.get("emoteSet", {}).get("manage", False)


class UserInfo(NamedTuple):
    id: str
    active_emote_set_id: str
    active_emote_set_name: str


class EmoteSetInfo(NamedTuple):
    name: str
    owner_id: str


#############################################################################################################################
# CLIENT
#############################################################################################################################


class StvClient:
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

    Attributes
    ----------
    session: ClientSession | None = None
        If provided, then the wrapper will use it as its session calls.
        Otherwise, it will create a new `ClientSession` on every API call.
    """

    def __init__(
        self,
        *,
        bot_7tv_user_id: str,
        bearer_token: str | None = None,
    ) -> None:
        self._bearer_token: str | None = bearer_token
        self.user_id: str = bot_7tv_user_id
        self.session = ClientSession()

    async def invoke(self, query: str, variables: Mapping[str, Any]) -> Any:
        """Invoke a request to 7TV GraphQL API.

        Parameters
        ----------
        query: str
            GraphQL query.
        variables: Mapping[str, Any]
            Dictionary of variables to be provided with query into `json` kwarg of GraphQL request.

            Mapping[str, Any] is type-hinting crunch to be compatible with TypedDict,
            this is supposed to be dict[str, Any].

        Returns
        -------
        dict[str, Any]
            GraphQL json dictionary from the response. Usually heavily nested.
        """
        match = re.search(r"^\s*(?:query|mutation)\s+(?P<query_name>\w+)\s*(?:\(|\{)", query)
        query_name = match.group("query_name") if match else "UnknownQuery"
        log.debug("7TV GraphQL - invoking query %s", query_name)

        try:
            async with (
                asyncio.timeout(STV_REQUEST_TIMEOUT),
                (self.session).post(
                    url="https://api.7tv.app/v4/gql",
                    json={"query": query, "variables": variables},
                    headers={"Authorization": f"Bearer {self._bearer_token}"}
                    if self._bearer_token is not None
                    else None,
                ) as response,
            ):
                if response.ok:
                    gql_json = await response.json(loads=orjson.loads)
                else:
                    msg = "7TV is unavailable/lagging/down"
                    log.warning(
                        "7TV response to %s was not ok. Status: %s Text:\n%s",
                        query_name,
                        response.status,
                        await response.text(),
                    )
                    raise ServiceError(msg) from None
        except TimeoutError:
            msg = "7TV is lagging, it didn't respond in time; try again later?"
            raise ServiceError(msg) from None

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
                raise UnauthorizedError(data={"gql_json": gql_json})
            case _:
                msg = "Something went wrong"
                raise errors.SomethingWentWrongError(msg, data={"gql_json": gql_json})

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
        if index < 0:
            msg = "Negative index is not allowed"
            raise UnsatisfyingResultError(msg)

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
            msg = f"Search result doesn't have that many emotes (only {len(emote_items)} total)"
            raise EmoteNotFoundError(msg) from None

    async def fetch_emote(self, emote_id: str) -> Emote:
        """Get defaultName for an emote.

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

    async def get_display_name_by_stv_id(self, stv_id: str) -> str:
        """Get user by stv id."""
        query = """
query GetUserInfo($userId: Id!) {
  users {
    user(id: $userId) {
      mainConnection {
        platformId
        platformDisplayName
      }
    }
  }
}
"""
        variables = {"userId": stv_id}
        res = await self.invoke(query, variables)
        return res["users"]["user"]["mainConnection"]["platformDisplayName"]
