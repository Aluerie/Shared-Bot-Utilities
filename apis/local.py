"""Local API.

In the past, I was running Dota 2 Client from steamIO in the same process as my twitch/discord bots.
However, there are seemingly multiple unsolvable issues that comes to such structure
* If steam is down (even Tuesday Maintenance) then both bots go down;
* steamIO has some issue with reconnecting to steam;

In the end, it seems that the best solution to this problem is run steam bot in a separate process so if
it dies/struggles then my twitch/discord bots are unaffected.

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
from typing import TYPE_CHECKING, Any, Final, override
from urllib.parse import quote

import aiohttp
from steam.ext.dota2 import GameMode, Hero, LobbyType

from shared import errors

if TYPE_CHECKING:
    from shared.typings import local as schemas

# Colors of the player slots in a Dota 2 match, in the order of the slots.
PLAYER_COLORS: Final = (
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
)


class MatchState(IntEnum):
    """Indicates current state for matches."""

    Starting = 1
    Live = 2
    Pending = 3
    Completed = 4
    GaveUp = 91


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
    """A streamer from the Dota2Bot's friend list and what they are doing at the moment."""

    def __init__(self, data: schemas.Friend) -> None:
        self.id: int = data["id"]
        self.name: str = data["name"]
        self.is_playing_dota: bool = data["is_playing_dota"]
        self.status: str = data["status"]
        self.rich_presence: str = data["rich_presence"]
        self.raw_rich_presence: dict[str, str] = data["raw_rich_presence"]
        self.party: list[int] = data["party"]
        self.live_match: FriendLiveMatch | None = FriendLiveMatch(data["live_match"]) if data["live_match"] else None


class FriendLiveMatch:
    """A match the streamer is currently playing or spectating.

    Most of the data is `None` or empty until the Dota2Bot manages to gather it.
    """

    def __init__(self, data: schemas.StreamerLiveMatch) -> None:
        self.id: int | None = data.get("id")
        self.game_mode: GameMode | None = GameMode.try_value(gm) if (gm := data.get("game_mode")) is not None else None
        self.lobby_type: LobbyType | None = (
            LobbyType.try_value(lt) if (lt := data.get("lobby_type")) is not None else None
        )
        self.tag: str = data["tag"]
        self.message: str = data["message"]
        self.server_steam_id: int | None = data["server_steam_id"]
        self.players: list[FriendLiveMatchPlayer] = [FriendLiveMatchPlayer(p) for p in data["players"]]
        self.average_mmr: int | None = data["average_mmr"]
        self.state: MatchState = MatchState(data["state"])


class FriendLiveMatchPlayer:
    """A player of a live match."""

    def __init__(self, data: schemas.StreamerLiveMatchPlayer) -> None:
        self.id: int = data["id"]
        self.player_slot: int = data["player_slot"]
        self.lifetime_games: int = data["lifetime_games"]
        self.rank_display_name: str = data["rank_display_name"]
        self.hero: Hero = Hero.try_value(data["hero_id"])

    @property
    def color(self) -> str:
        """Color of the player's slot."""
        return PLAYER_COLORS[self.player_slot] if 0 <= self.player_slot < len(PLAYER_COLORS) else "Colorless"

    @property
    def identifier(self) -> str:
        """How to call the player in chat: by their hero, or by their color if the hero is not picked yet."""
        return self.hero.name if self.hero else self.color


class MatchBase:
    """Data common for all kinds of finished matches."""

    def __init__(self, *, match_id: int, game_mode: int, lobby_type: int, start_time: str, duration: int) -> None:
        self.id: int = match_id
        self.game_mode: GameMode = GameMode.try_value(game_mode)
        self.lobby_type: LobbyType = LobbyType.try_value(lobby_type)
        self.start_dt: dt.datetime = dt.datetime.fromisoformat(start_time)
        self.duration: dt.timedelta = dt.timedelta(seconds=duration)

    @property
    def end_dt(self) -> dt.datetime:
        """When the match has ended."""
        return self.start_dt + self.duration

    @property
    def category(self) -> Category:
        """Category of the match for the !wl command."""
        return Category.create(self.lobby_type, self.game_mode)


class MinimalMatch(MatchBase):
    """Minimal information about a match: scores and players' KDA."""

    def __init__(self, data: schemas.MinimalMatch) -> None:
        super().__init__(
            match_id=data["id"],
            game_mode=data["game_mode"],
            lobby_type=data["lobby_type"],
            start_time=data["start_time"],
            duration=data["duration"],
        )
        self.players: list[MinimalMatchPlayer] = [MinimalMatchPlayer(p) for p in data["players"]]
        self.radiant_score: int = data["radiant_score"]
        self.dire_score: int = data["dire_score"]

    @override
    def __repr__(self) -> str:
        return f"<MinimalMatch id={self.id}>"


class MinimalMatchPlayer:
    """A player of a minimal match."""

    def __init__(self, data: schemas.MinimalMatchPlayer) -> None:
        self.id: int = data["id"]
        self.hero: Hero = Hero.try_value(data["hero_id"])
        self.kills: int = data["kills"]
        self.deaths: int = data["deaths"]
        self.assists: int = data["assists"]

    @override
    def __repr__(self) -> str:
        return f"<MinimalMatchPlayer id={self.id} hero={self.hero!r}>"


class PreviousMatch(MatchBase):
    """A match from the account's match history."""

    def __init__(self, data: schemas.PreviousMatch) -> None:
        super().__init__(
            match_id=data["id"],
            game_mode=data["game_mode"],
            lobby_type=data["lobby_type"],
            start_time=data["start_time"],
            duration=data["duration"],
        )
        self.hero: Hero = Hero.try_value(data["hero_id"])
        self.win: bool = data["win"]
        self.abandon: bool = data["abandon"]

    @override
    def __repr__(self) -> str:
        return f"<PreviousMatch id={self.id} hero={self.hero!r} win={self.win}>"


class ProfileCard:
    """Dota 2 profile card of an account."""

    def __init__(self, data: schemas.ProfileCard) -> None:
        self.rank_display_name: str = data["rank_display_name"]

    @override
    def __repr__(self) -> str:
        return f"<ProfileCard rank={self.rank_display_name}>"


class SteamUser:
    """A Steam user."""

    def __init__(self, data: schemas.SteamUser) -> None:
        self.id: int = data["id"]
        self.name: str = data["name"]

    @override
    def __repr__(self) -> str:
        return f"<SteamUser id={self.id} name={self.name!r}>"


class LocalAPI:
    """Client for the local API provided by my Dota2Bot."""

    BASE_URL: Final = "http://127.0.0.1:8000"

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session: aiohttp.ClientSession = session

    async def _invoke(self, endpoint: str, **params: str | int) -> Any:
        try:
            async with self.session.get(
                f"{self.BASE_URL}{endpoint}",
                params=params or None,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                ok = resp.ok
        except aiohttp.ClientError, TimeoutError, ValueError:
            msg = "It seems Dota2Bot is down, please ask Irene to fix it"
            raise errors.RespondWithError(msg) from None

        if ok:
            return data

        detail = data.get("detail") if isinstance(data, dict) else None
        if isinstance(detail, str):
            raise errors.RespondWithError(detail)
        # FastAPI sends a list as `detail` when it rejects the request itself (HTTP 422)
        msg = "Dota2Bot didn't understand the request, please ask Irene to fix it"
        raise errors.RespondWithError(msg)

    async def get_friend(self, friend_id: int) -> Friend:
        """Get a streamer from the Dota2Bot's friend list.

        Parameters
        ----------
        friend_id
            Steam friend id (account id) of the streamer.
        """
        data: schemas.Friend = await self._invoke(f"/friend/{friend_id}")
        return Friend(data)

    async def get_minimal_match(self, match_id: int) -> MinimalMatch:
        """Get minimal information about a finished match."""
        data: schemas.MinimalMatch = await self._invoke(f"/minimal/{match_id}")
        return MinimalMatch(data)

    async def get_profile_card(self, friend_id: int) -> ProfileCard:
        """Get Dota 2 profile card of an account."""
        data: schemas.ProfileCard = await self._invoke(f"/profile_card/{friend_id}")
        return ProfileCard(data)

    async def get_previous_match(self, friend_id: int, index: int = 0) -> PreviousMatch:
        """Get a match from the account's match history.

        Parameters
        ----------
        friend_id
            Steam friend id (account id).
        index
            How far to look back: 0 is the latest match, 1 is the one before it, and so on.
        """
        data: schemas.PreviousMatch = await self._invoke(f"/previous_match/{friend_id}", index=index)
        return PreviousMatch(data)

    async def get_steam_user(self, friend_id: int) -> SteamUser:
        """Get a Steam user by their friend id (account id)."""
        data: schemas.SteamUser = await self._invoke(f"/steam_user/{friend_id}")
        return SteamUser(data)

    async def get_steam_user_convert(self, argument: str) -> SteamUser:
        """Get a Steam user by any kind of Steam ID or by a profile url."""
        data: schemas.SteamUser = await self._invoke(f"/steam_user_convert/{quote(argument, safe='')}")
        return SteamUser(data)

    async def get_accept_invite(self, friend_id: int, twitch_id: str) -> SteamUser:
        """Allow the Dota2Bot to accept a friend invite from the Steam user for the next few minutes."""
        data: schemas.SteamUser = await self._invoke("/accept_invite/", friend_id=friend_id, twitch_id=twitch_id)
        return SteamUser(data)
