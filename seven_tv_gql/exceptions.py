from __future__ import annotations

from typing import Any

from .. import errors

__all__ = (
    "ConflictingEmoteNameError",
    "EmoteNotFoundInSetError",
    "LackingPrivilegesError",
)


class SevenTVError(errors.CustomError):
    """Error Class for Seven TV Errors.

    I mean this class to be used for those errors that comes from 7TV API directly, i.e. in `message` field.
    """


class InvokeQueryError(SevenTVError):
    """TransportQueryError."""

    def __init__(self, status: Any, message: Any, code: Any) -> None:
        self.status = status
        self.message = message
        self.code = code
        super().__init__(f"{status} {message}")


class EmoteNotFoundInSetError(SevenTVError, errors.RespondWithError):
    """Emote Not Found In Set Error."""


class ConflictingEmoteNameError(SevenTVError, errors.RespondWithError):
    """Conflicting Emote Name Error."""


class LackingPrivilegesError(SevenTVError, errors.RespondWithError):
    """Lacking Privileges Error."""
