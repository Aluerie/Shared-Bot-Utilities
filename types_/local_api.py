from __future__ import annotations

from typing import Literal, TypedDict

from shared.local_api.client import MatchState  # ruff: ignore[typing-only-first-party-import]

type TagLiteral = Literal["playing", "spectating", "unsupported"]

#############################################################################################################################
# ENDPOINTS
#############################################################################################################################


class MinimalMatch(TypedDict):
    """/minimal/{match_id} Endpoint."""

    id: int
    players: list[MinimalMatchPlayer]
    outcome: int  # MatchOutcome
    game_mode: int  # GameMode
    lobby_type: int  # LobbyType
    radiant_score: int
    dire_score: int
    start_time: str
    duration: int


class MinimalMatchPlayer(TypedDict):
    id: int
    hero_id: int  # Hero
    kills: int
    deaths: int
    assists: int


class PreviousMatch(TypedDict):
    """/previous_match/{friend_id} Endpoint."""

    id: int
    hero_id: int  # Hero
    win: bool
    abandon: bool
    game_mode: int  # GameMode
    lobby_type: int  # LobbyType
    start_time: str
    duration: int


class ProfileCard(TypedDict):
    """/profile_card/{friend_id} Endpoint."""

    rank_display_name: str


class SteamUser(TypedDict):
    """/steam_user/{friend_id} Endpoint."""

    id: int
    name: str


class Streamer(TypedDict):
    id: int
    name: str
    is_playing_dota: bool
    status: str
    rich_presence: str
    raw_rich_presence: dict[str, str]
    activity: str
    live_match: StreamerLiveMatch | None


class StreamerLiveMatch(TypedDict):
    id: int | None
    game_mode: int | None  # GameMode
    lobby_type: int | None  # LobbyType
    tag: TagLiteral
    message: str
    server_steam_id: int | None
    players: list[StreamerLiveMatchPlayer]
    started_at: str
    average_mmr: int | None
    state: MatchState


class StreamerLiveMatchPlayer(TypedDict):
    id: int
    player_slot: int
    lifetime_games: int
    rank_display_name: str
    hero_id: int  # Hero
