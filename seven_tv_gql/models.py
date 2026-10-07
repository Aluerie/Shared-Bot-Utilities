"""7TV Models.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, NamedTuple, NotRequired, TypedDict, cast, override

from . import exceptions
from .constants import COMMON_WORDS, EMOTE_SET_EMOTES_CAPACITY_LIMIT

if TYPE_CHECKING:
    from .client import GraphQL7TVClient

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
    "Emote",
    "PartialEmote",
    "PartialEmoteSet",
    "PartialUser",
)

COMMON_EMOTE_SUB_QUERY = """
id
ownerId
defaultName
flags {
    animated
}"""


class PartialEmote:
    """Partial Emote."""

    def __init__(self, client: GraphQL7TVClient, emote_id: str) -> None:
        self._client: GraphQL7TVClient = client
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

    def __init__(self, client: GraphQL7TVClient, data: EmotePayload) -> None:
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
        client: GraphQL7TVClient,
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

    def __init__(self, client: GraphQL7TVClient, emote_set_id: str) -> None:
        self._client: GraphQL7TVClient = client
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
            Emote's `alias` in the mentioned emote set. If alias wasn't set, it still returns `defaultName` for the emote.
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

        emote = res["emotes"]["emote"]["inEmoteSets"][0]["emote"]
        if emote is None:
            msg = f"Could not find {emote_id} in emote set {self.id}"
            raise exceptions.EmoteNotFoundError(msg)
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
        except exceptions.InvokeQueryError as error:
            if error.message == "BAD_REQUEST emote not found in set":
                msg = "Emote was not found in set"
                raise exceptions.EmoteNotFoundError(msg) from None
            raise

    async def validate_emote_alias_not_a_common_word(
        self,
        emote_id: str,
        emote_alias: str | None = None,
        *,
        allow_common_words: bool = True,
    ) -> None:
        """Validate if emote_alias is not a common word."""
        if allow_common_words:
            return

        if emote_alias is None:
            # we have to check emote's default name
            emote = await self._client.fetch_emote(emote_id)
            emote_alias = emote.default_name
        if emote_alias in COMMON_WORDS:
            msg = "Common words are not allowed to be used as emote aliases for this emote set"
            raise exceptions.InvalidEmoteAliasError(msg)

    async def add_emote(
        self,
        emote_id: str,
        *,
        emote_alias: str | None = None,
        allow_common_words: bool = True,
    ) -> None:
        """Add an emote to a 7TV emote set.

        Parameters
        ----------
        emote_id: str
            7TV emote id.
        emote_alias: str | None = None
            If provided then the emote will be added with an alias.
        allow_common_words: bool = True
            Whether to reject usage of common words as emote_alias or emote name.
        """
        await self.validate_emote_alias_not_a_common_word(emote_id, emote_alias, allow_common_words=allow_common_words)

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
        except exceptions.InvokeQueryError as error:
            match error.message:
                case "BAD_REQUEST this emote has a conflicting name":
                    try:
                        # TODO: Maybe remove this, why do we do an extra request
                        await self.fetch_emote_alias(emote_id)
                    except exceptions.EmoteNotFoundError:
                        msg = "This emote has a conflicting name"
                        raise exceptions.ConflictingEmoteNameError(msg) from None
                    else:
                        msg = "This emote is already present in the emote set"
                        raise exceptions.UnsatisfyingResultError(msg) from None
                case m if "invalid emote alias" in m:
                    msg = "Invalid emote alias"
                    raise exceptions.InvalidEmoteAliasError(msg) from None
                case "LOAD_ERROR emote set is at capacity":
                    msg = "Emote set is at full capacity"
                    raise exceptions.UnsatisfyingResultError(msg) from None
                case _:
                    raise

    async def rename_emote(
        self,
        emote_id: str,
        *,
        new_emote_alias: str,
        old_emote_alias: str | None = None,
        allow_common_words: bool = True,
    ) -> None:
        """Rename 7tv emote."""
        await self.validate_emote_alias_not_a_common_word(emote_id, new_emote_alias, allow_common_words=allow_common_words)

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
        except exceptions.InvokeQueryError as error:
            match error.message:
                case "BAD_REQUEST emote name conflict":
                    msg = "Emote name conflict"
                    raise exceptions.ConflictingEmoteNameError(msg) from None
                case "BAD_REQUEST emote not found in set":
                    msg = "Emote not found in the emote set"
                    raise exceptions.EmoteNotFoundError(msg) from None
                case m if "invalid emote alias" in m:
                    msg = "Invalid emote alias"
                    raise exceptions.InvalidEmoteAliasError(msg) from None
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
    }
  }
}
        """,
            variables={"emoteSetId": self.id},
        )
        emote_set = res["emoteSets"]["emoteSet"]
        return EmoteSetInfo(name=emote_set["name"])

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
            raise exceptions.EmoteNotFoundError(msg) from None


class PartialUser:
    """Partial Emote Set."""

    def __init__(self, client: GraphQL7TVClient, twitch_id: str) -> None:
        self._client: GraphQL7TVClient = client
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
        str
            Emote ID that matches provided `emote_name` in the active emote set for the broadcaster.
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
            raise exceptions.UnsatisfyingResultError(msg)
        return PartialEmote(self._client, candidate["id"])

    async def check_bot_editor(self) -> EditorCheck:
        """Check bot editor for."""
        res: GetUserEditors = cast(
            "GetUserEditors",
            await self._client.invoke(
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
            ),
        )
        bot_editor = next(
            iter([
                editor
                for editor in res["users"]["userByConnection"]["editors"]
                if editor["editorId"] == self._client.user_id
            ]),
            None,
        )
        if bot_editor is None:
            msg = "The bot is yet to receive a 7tv editor request from the streamer"
            raise exceptions.UnsatisfyingResultError(msg)

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
        except exceptions.InvokeQueryError as error:
            match error.message:
                case "BAD_REQUEST editor is not pending":
                    msg = (
                        "7TV editor request was already accepted"
                        if (await self.check_bot_editor()).state == "ACCEPTED"
                        else "7TV editor request is not pending"
                    )
                    raise exceptions.UnsatisfyingResultError(msg) from None
                case "LOAD_ERROR user editor not found":
                    msg = "I don't see any 7TV editor requests from this streamer (have you sent it?)"
                    raise exceptions.UnsatisfyingResultError(msg) from None
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
