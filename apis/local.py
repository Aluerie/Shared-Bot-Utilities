"""Local API.

In the past, I was running Dota 2 Client from steamIO in the same process as my twitch/discord bots.
However, there are seemingly multiple unsolvable issues that comes to such structure
* If steam is down (even Tuesday Maintenance) then both bots go down;
* steamIO has some issue with reconnecting to steam;

In the end, it seems that the best solution to this problem is run steam bot in a separate process so if it dies/struggles
then my twitch/discord bots are unaffected.

So currently, Dota2Bot hosts its API at localhost:8000.
Mostly, Dota 2 and steam related functionality. Maybe more incoming in future.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum, IntEnum
from typing import TYPE_CHECKING, Any, TypedDict, Unpack, override

from steam.ext.dota2 import GameMode, Hero, LobbyType

from shared import errors

if TYPE_CHECKING:
    import aiohttp

    from shared.types_ import local_api as schemas


class MatchState(IntEnum):
    """Indicates current state for matches."""

    Starting = 1
    Live = 2
    Pending = 3
    Completed = 4
    ApiError = 91


class Category(Enum):
    """Match categories for !score (!wl !winloss) command.

    The bot will group matches into !wl command by this parameter, i.e. !wl -> "Ranked 3 W - 1 L, Turbo 2 W - 0 L."
    """

    Ranked = 1
    Unranked = 2
    Turbo = 3
    Other = 4

    @classmethod
    def create(cls, lobby_type: int, game_mode: int) -> Category:
        """Create !wl command category from `lobby_type` and `game_mode`.

        Dota Matches naturally in API data are described by those attributes.
        This allows categorizing dota matches for !wl command.
        """
        match lobby_type:
            case LobbyType.Ranked:
                return Category.Ranked
            case LobbyType.Unranked:
                return Category.Turbo if game_mode == GameMode.Turbo else Category.Unranked
            case _:
                return Category.Other


class Friend:
    """Friend."""

    def __init__(self, data: schemas.Friend) -> None:
        self.id: int = data["id"]
        self.name: str = data["name"]
        self.is_playing_dota: bool = data["is_playing_dota"]
        self.status: str = data["status"]
        self.rich_presence: str = data["rich_presence"]
        self.raw_rich_presence: dict[str, str] = data["raw_rich_presence"]
        self.activity: str = data["activity"]
        self.live_match: FriendLiveMatch | None = FriendLiveMatch(data["live_match"]) if data["live_match"] else None


class FriendLiveMatch:
    """FriendLiveMatch."""

    def __init__(self, data: schemas.StreamerLiveMatch) -> None:
        self.id: int | None = data.get("id")
        self.game_mode: GameMode | None = GameMode.try_value(gm) if (gm := data.get("game_mode")) is not None else None
        self.lobby_type: LobbyType | None = LobbyType.try_value(lt) if (lt := data.get("lobby_type")) is not None else None
        self.tag: str = data["tag"]
        self.message: str = data["message"]
        self.server_steam_id: int | None = data["server_steam_id"]
        self.players = [FriendLiveMatchPlayer(p) for p in data["players"]]
        self.average_mmr: int | None = data["average_mmr"]
        self.state: MatchState = data["state"]


class FriendLiveMatchPlayer:
    """FriendLiveMatchPlayer."""

    def __init__(self, data: schemas.StreamerLiveMatchPlayer) -> None:
        self.id: int = data["id"]
        self.player_slot: int = data["player_slot"]
        self.lifetime_games: int = data["lifetime_games"]
        self.rank_display_name: str = data["rank_display_name"]
        self.hero: Hero = Hero.try_value(data["hero_id"])

    @property
    def color(self) -> str:
        """Color."""
        colors = [
            "Blue",
            "Teal",
            "Purple",
            "Yellow",
            "Orange",
            "Pink",
            "Olive",
            "LightBlue",
            "DarkGreen",
            "Brown",
        ]
        try:
            return colors[self.player_slot]
        except IndexError:
            return "Colorless"

    @property
    def identifier(self) -> str:
        """Identifier."""
        return self.hero.name if self.hero else self.color


class MatchBaseKwargs(TypedDict):
    """MatchBaseKwargs."""

    id: int
    game_mode: int
    lobby_type: int


class MatchBase:
    """MatchBase."""

    def __init__(self, **kwargs: Unpack[MatchBaseKwargs]) -> None:
        self.id = kwargs.get("id")
        self.game_mode: GameMode = GameMode.try_value(kwargs.get("game_mode"))
        self.lobby_type: LobbyType = LobbyType.try_value(kwargs.get("lobby_type"))

    @property
    def category(self) -> Category:
        """Category."""
        return Category.create(self.lobby_type, self.game_mode)


class MinimalMatch(MatchBase):
    """Minimal."""

    def __init__(self, data: schemas.MinimalMatch) -> None:
        super().__init__(**data)
        self.players = [MinimalMatchPlayer(p) for p in data["players"]]
        self.radiant_score: int = data["radiant_score"]
        self.dire_score: int = data["dire_score"]
        self.start_dt: dt.datetime = dt.datetime.fromisoformat(data["start_time"])
        self.duration: dt.timedelta = dt.timedelta(seconds=data["duration"])

    @override
    def __repr__(self) -> str:
        return f"<MinimalMatch id={self.id}>"


class MinimalMatchPlayer:
    """MinimalMatchPlayer."""

    def __init__(self, data: schemas.MinimalMatchPlayer) -> None:
        self.id = data["id"]
        self.hero: Hero = Hero.try_value(data["hero_id"])
        self.kills: int = data["kills"]
        self.deaths: int = data["deaths"]
        self.assists: int = data["assists"]

    @override
    def __repr__(self) -> str:
        return f"<MinimalMatchPlayer id={self.id} hero={self.hero!r}>"


class PreviousMatch(MatchBase):
    """PreviousMatch."""

    def __init__(self, data: schemas.PreviousMatch) -> None:
        super().__init__(**data)
        self.hero: Hero = Hero.try_value(data["hero_id"])
        self.win: bool = data["win"]
        self.abandon: bool = data["abandon"]
        self.start_dt: dt.datetime = dt.datetime.fromisoformat(data["start_time"])
        self.duration: dt.timedelta = dt.timedelta(seconds=data["duration"])

    @property
    def end_dt(self) -> dt.datetime:
        """end_dt."""
        return self.start_dt + self.duration

    @override
    def __repr__(self) -> str:
        return f"<PreviousMatch id={self.id} hero={self.hero!r} win={self.win}>"


class ProfileCard:
    """ProfileCard."""

    def __init__(self, data: schemas.ProfileCard) -> None:
        self.rank_display_name: str = data["rank_display_name"]

    @override
    def __repr__(self) -> str:
        return f"<ProfileCard rank={self.rank_display_name}>"


class SteamUser:
    """SteamUser."""

    def __init__(self, data: schemas.SteamUser) -> None:
        self.id: int = data["id"]
        self.name: str = data["name"]

    @override
    def __repr__(self) -> str:
        return f"<SteamUser id={self.id} name={self.name!r}>"


class LocalAPI:
    """Local API provided by my Dota2Bot."""

    BASE_URL = "http://127.0.0.1:8000"

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session

    async def _invoke(self, endpoint: str) -> Any:
        async with self.session.get(url=f"{self.BASE_URL}{endpoint}") as resp:
            data = await resp.json()
            if resp.ok:
                return data

            detail = data.get("detail")
            if detail is not None:
                raise errors.RespondWithError(detail)
            msg = "It seems Dota2Bot is down, please ask Irene to fix it"
            raise errors.RespondWithError(msg)

    async def get_friend(self, friend_id: int) -> Friend:
        """Get friend."""
        data: schemas.Friend = await self._invoke(endpoint=f"/friend/{friend_id}")
        return Friend(data)

    async def get_minimal_match(self, match_id: int) -> MinimalMatch:
        """Get minimal match."""
        data: schemas.MinimalMatch = await self._invoke(endpoint=f"/minimal/{match_id}")
        return MinimalMatch(data)

    async def get_profile_card(self, friend_id: int) -> ProfileCard:
        """Get profile card."""
        data = await self._invoke(endpoint=f"/profile_card/{friend_id}")
        return ProfileCard(data)

    async def get_previous_match(self, friend_id: int) -> PreviousMatch:
        """Get previous match."""
        data: schemas.PreviousMatch = await self._invoke(endpoint=f"/previous_match/{friend_id}")
        return PreviousMatch(data)

    async def get_steam_user(self, friend_id: int) -> SteamUser:
        """Get steam user."""
        data: schemas.SteamUser = await self._invoke(endpoint=f"/steam_user/{friend_id}")
        return SteamUser(data)

    async def get_steam_user_convert(self, argument: str) -> SteamUser:
        """Get steam id. Converts ID from ID/URL to friend ID."""
        data: schemas.SteamUser = await self._invoke(endpoint=f"/steam_user_convert/{argument}")
        return SteamUser(data)
