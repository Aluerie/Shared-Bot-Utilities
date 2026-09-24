from __future__ import annotations

from typing import Literal, TypedDict

__all__ = ("GetUserEditors",)

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
