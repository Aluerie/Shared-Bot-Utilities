"""Local Schemas.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from shared.apis.local import MatchState  # ruff: ignore[typing-only-first-party-import]

__all__ = (
    "Friend",
    "MinimalMatch",
    "PreviousMatch",
    "ProfileCard",
    "SteamUser",
)


type TagLiteral = Literal["playing", "spectating", "unsupported"]

#############################################################################################################################
# ENDPOINTS
#############################################################################################################################


class Friend(TypedDict):
    """/friend/{friend_id} Endpoint."""

    id: int
    name: str
    is_playing_dota: bool
    status: str
    rich_presence: str
    party: list[int]
    raw_rich_presence: dict[str, str]
    live_match: StreamerLiveMatch | None


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
    """/match_history/{friend_id} Endpoint."""

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
