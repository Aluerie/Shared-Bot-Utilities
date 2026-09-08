"""CUSTOM ERRORS.

All exceptions raised by me should be defined in this file.
It's just my small code practice.

License
-------
* This Source Code Form is subject to the terms of the [Mozilla Public License v2.0](<http://mozilla.org/MPL/2.0/>).
* Copyright (C) 2020-present [@Aluerie](<https://github.com/Aluerie>).
"""

from __future__ import annotations

from typing import Any


class CustomError(Exception):
    """The base exception for my (@Aluerie) projects. All other exceptions should inherit from this."""


class SilentError(CustomError):
    """Errors to be ignored by error handlers."""


class APIDataError(CustomError):
    """API Data Error.

    This error is raised when 3rd party API returns a response indicating
    that there was some error.

    Useful for API like GraphQL which like to put an error message into its data responses, i.e.
    `{data: {"error": "There was an error"}}`.

    Attributes
    ----------
    data: Any
        Any data that API attached to the response.
    """

    def __init__(self, message: str, data: Any) -> None:
        self.data: Any = data
        super().__init__(message)


class BadUserInputError(CustomError):
    """Error indicating there was a problem with user input."""


class UnsatisfyingResultError(CustomError):
    """Error indicating that the result of operation was unsatisfying.

    Useful for API calls where the response was correct, but, for example,
    some conditions were not met.
    """
