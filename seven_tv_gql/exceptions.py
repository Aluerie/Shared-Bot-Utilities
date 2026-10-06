"""Seven TV Exceptions.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

from typing import Any

from shared import errors

__all__ = (
    "ConflictingEmoteNameError",
    "EmoteNotFoundError",
    "InvalidEmoteAliasError",
    "InvokeQueryError",
    "LackingPrivilegesError",
    "ServiceError",
    "SevenTVError",
    "SomethingWentWrongError",
    "UnauthorizedError",
    "UnsatisfyingResultError",
)


class SevenTVError(errors.CustomError):
    """Error Class for Seven TV Errors.

    I mean this class to be used for those errors that comes from 7TV API directly, i.e. in `message` field.
    """


class UnauthorizedError(SevenTVError):
    """Unauthorized."""

    def __init__(
        self,
        message: str,
        **debug_data_kwargs: Any,
    ) -> None:
        super().__init__(message)
        self.message: str = message
        self.debug_data: dict[str, Any] = debug_data_kwargs


class InvokeQueryError(SevenTVError):
    """TransportQueryError."""

    def __init__(self, status: Any, message: Any, code: Any) -> None:
        self.status = status
        self.message = message
        self.code = code
        super().__init__(f"{status} {message}")


class UnsatisfyingResultError(SevenTVError):
    """UnsatisfyingResultError."""


class ServiceError(UnsatisfyingResultError):
    """Service Error."""


class EmoteNotFoundError(UnsatisfyingResultError):
    """Emote Not Found In Set Error."""


class ConflictingEmoteNameError(UnsatisfyingResultError):
    """Conflicting Emote Name Error."""


class LackingPrivilegesError(UnsatisfyingResultError):
    """Lacking Privileges Error."""


class InvalidEmoteAliasError(UnsatisfyingResultError):
    """Invalid Emote Alias Error."""


class SomethingWentWrongError(SevenTVError):
    """SomethingWentWrongError."""

    def __init__(
        self,
        message: str,
        **debug_data_kwargs: Any,
    ) -> None:
        super().__init__(message)
        self.message: str = message
        self.debug_data: dict[str, Any] = debug_data_kwargs
