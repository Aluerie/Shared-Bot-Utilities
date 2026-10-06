"""SevenTV GraphQL requests.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

from typing import Literal, TypedDict

__all__ = (
    "GetUserEditors",
    "TopSearchByEmoteName",
)

#####################
# CheckBotEditorFor #
#####################


class GetUserEditors(TypedDict):
    """seven_tv.client.check_bot_editor_for."""

    users: GUEUsers


class GUEUsers(TypedDict):
    userByConnection: GUEUserByConnection


class GUEUserByConnection(TypedDict):
    editors: list[GUEEditors]


class GUEEditors(TypedDict):
    editorId: str
    state: Literal["PENDING", "ACCEPTED", "REJECTED"]
    permissions: GUEPermissions


class GUEPermissions(TypedDict):
    emoteSet: GUEEmoteSetPermissions


class GUEEmoteSetPermissions(TypedDict):
    manage: bool


########################
# TopSearchByEmoteName #
########################


class TopSearchByEmoteName(TypedDict):
    """TopSearchByEmoteName."""

    emotes: TPSBENEmotes


class TPSBENEmotes(TypedDict):
    search: TPSBENSearch


class TPSBENSearch(TypedDict):
    items: list[TPSBENItem]


class TPSBENItem(TypedDict):
    id: str
    defaultName: str
