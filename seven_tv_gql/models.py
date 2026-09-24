from __future__ import annotations

from typing import TYPE_CHECKING, Literal, NamedTuple, NotRequired, TypedDict, cast

from shared.types_.seven_tv import GetUserEditors

from .. import errors
from ..globs import Global7TV
from .exceptions import ConflictingEmoteNameError, EmoteNotFoundInSetError, InvokeQueryError

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

    from ..types_.seven_tv import GetUserEditors, GUEEditors


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
            """  # noqa: UP031
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


class EmoteSetEmote(Emote):
    """Emote Set Emote."""

    def __init__(
        self,
        client: GraphQL7TVClient,
        data: EmotePayload,
        alias: str,
        partial_emote_set: PartialEmoteSet,
    ) -> None:
        super().__init__(client, data)
        self.alias: str = alias
        self.partial_emote_set: PartialEmoteSet = partial_emote_set


class PartialEmoteSet:
    """Partial Emote Set."""

    def __init__(self, client: GraphQL7TVClient, emote_set_id: str) -> None:
        self._client: GraphQL7TVClient = client
        self.id: str = emote_set_id

    async def fetch_emote_alias(self, emote_id: str) -> str:
        """
        Get emote's alias in the emote alias.

        Parameters
        ----------
        emote_set_id: str
            7TV emote set where we will search for the emote.
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
            raise EmoteNotFoundInSetError(msg)
        return emote["alias"]

    async def remove_emote(self, emote_id: str) -> PartialEmote:
        """
        Remove an emote from the emote set.

        Parameters
        ----------
        broadcaster_id: str
            Twitch ID for the broadcaster.
        emote_name: str
            Emote name to query against.

        Returns
        -------
        str
            `emote_set_id`, which is pretty illogical and not useful.
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
            res = await self._client.invoke(query, variables=variables)
        except InvokeQueryError as error:
            if error.message == "BAD_REQUEST emote not found in set":
                msg = str(error)
                raise EmoteNotFoundInSetError(msg) from None
            raise

        return PartialEmote(self._client, res["emoteSets"]["emoteSet"]["removeEmote"]["id"])

    async def add_emote(self, emote_id: str, *, emote_alias: str | None = None) -> PartialEmote:
        """
        Add an emote to a 7TV emote set.

        Parameters
        ----------
        emote_id: str
            7TV emote id.
        emote_alias: str | None = None
            If provided then the emote will be added with an alias.

        Returns
        -------
        str
            `emote_set_id`, which is pretty illogical and not useful.
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
}"""
        variables = {
            "emoteSetId": self.id,
            "emoteIdWithAlias": {"emoteId": emote_id, "alias": emote_alias},
        }
        try:
            res = await self._client.invoke(query, variables)
        except InvokeQueryError as error:
            if error.message == "BAD_REQUEST this emote has a conflicting name":
                try:
                    await self.fetch_emote_alias(emote_id)
                except EmoteNotFoundInSetError:
                    # This means the new emote has a conflicting name
                    msg = "This emote has a conflicting name"
                    raise ConflictingEmoteNameError(msg) from None
                else:
                    msg = "This emote is already present in the emote set"
                    raise errors.RespondWithError(msg) from None
            raise

        return PartialEmote(self._client, res["emoteSets"]["emoteSet"]["addEmote"]["id"])

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


class PartialUser:
    """Partial Emote Set."""

    def __init__(self, client: GraphQL7TVClient, twitch_id: str) -> None:
        self._client: GraphQL7TVClient = client
        self.twitch_id: str = twitch_id

    # async def get_linked_emote_set_id(self):

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
        broadcaster_id: str
            Twitch ID for the broadcaster.
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
        candidate = next((c for c in candidates if c["alias"] == emote_name), None)
        if candidate is None:
            msg = f"Could not find an emote named {emote_name} in the first 20 results of 7TV query."
            raise errors.UnsatisfyingResultError(msg)
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
            iter(
                [
                    editor
                    for editor in res["users"]["userByConnection"]["editors"]
                    if editor["editorId"] == self._client.user_id
                ]
            ),
            None,
        )
        if bot_editor is None:
            msg = "The bot is yet to receive a 7tv editor request from the streamer"
            raise errors.RespondWithError(msg)

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
            message = error.message

            respond = ""
            if message == "BAD_REQUEST editor is not pending":
                bot_editor = await self.check_bot_editor()
                if bot_editor.state == "ACCEPTED":
                    respond = f"7TV editor request was already accepted {Global7TV.FeelsDankMan}"
                else:
                    respond = f"7TV editor request is not pending {Global7TV.FeelsDankMan}"
            elif message == "LOAD_ERROR user editor not found":
                respond = (
                    f"I don't see any 7TV editor requests from this streamer (have you sent it?) {Global7TV.FeelsDankMan}"
                )
            if respond:
                raise errors.RespondWithError(respond) from None
            raise

        return res["userEditors"]["editor"]["updateState"]["state"]


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
