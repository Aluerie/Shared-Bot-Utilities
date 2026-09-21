from __future__ import annotations

from typing import TYPE_CHECKING, NotRequired, TypedDict

from .. import errors
from .exceptions import EmoteNotFoundInSetError

if TYPE_CHECKING:
    from .client import SevenTVClient

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


__all__ = (
    "Emote",
    "PartialEmote",
    "PartialEmoteSet",
    "PartialUser",
)


class PartialEmote:
    """Partial Emote."""

    def __init__(self, client: SevenTVClient, emote_id: str) -> None:
        self._client: SevenTVClient = client
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
                        id
                        ownerId
                        defaultName
                        flags {
                            animated
                        }
                    }
                }
            }
            """,
            variables={
                "emoteId": self.id,
            },
        )
        emote: EmotePayload = res["data"]["emotes"]["emote"]
        return Emote(self._client, emote)


class Emote(PartialEmote):
    """Emote."""

    def __init__(self, client: SevenTVClient, data: EmotePayload) -> None:
        super().__init__(client, data.get("id"))
        self.owner_id: str = data.get("ownerId")
        self.default_name: str = data.get("defaultName")
        self.animated = self._animated = data["flags"]["animated"]


class EmoteSetEmote(Emote):
    """Emote Set Emote."""

    def __init__(
        self,
        client: SevenTVClient,
        data: EmotePayload,
        alias: str,
        partial_emote_set: PartialEmoteSet,
    ) -> None:
        super().__init__(client, data)
        self.alias: str = alias
        self.partial_emote_set: PartialEmoteSet = partial_emote_set


class PartialEmoteSet:
    """Partial Emote Set."""

    def __init__(self, client: SevenTVClient, emote_set_id: str) -> None:
        self._client: SevenTVClient = client
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
                            inEmoteSets (emoteSetIds: [$emoteSetId]) {
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
        emote = res["data"]["emotes"]["emote"]["inEmoteSets"][0]["emote"]
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
        res = await self._client.invoke(
            query,
            variables={
                "emoteSetId": self.id,
                "emoteIdWithAlias": {
                    "emoteId": emote_id,
                },
            },
        )
        return PartialEmote(self._client, res["data"]["emoteSets"]["emoteSet"]["removeEmote"]["id"])

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
        query: str = """
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
        variables: AddEmoteVariables = {
            "emoteSetId": self.id,
            "emoteIdWithAlias": {"emoteId": emote_id},
        }
        if emote_alias:
            variables["emoteIdWithAlias"]["alias"] = emote_alias

        res = await self._client.invoke(
            query,
            variables=variables,
        )
        return PartialEmote(self._client, res["data"]["emoteSets"]["emoteSet"]["addEmote"]["id"])


class PartialUser:
    """Partial Emote Set."""

    def __init__(self, client: SevenTVClient, twitch_id: str) -> None:
        self._client: SevenTVClient = client
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
        return PartialEmoteSet(self._client, res["data"]["users"]["userByConnection"]["style"]["activeEmoteSetId"])

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
        candidates = res["data"]["users"]["userByConnection"]["style"]["activeEmoteSet"]["emotes"]["items"]
        candidate = next((c for c in candidates if c["alias"] == emote_name), None)
        if candidate is None:
            msg = f"Could not find an emote named {emote_name} in the first 20 results of 7TV query."
            raise errors.UnsatisfyingResultError(msg)
        return PartialEmote(self._client, candidate["id"])
