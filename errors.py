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
    data: Any | None
        Any data that API attached to the response.
    """

    def __init__(self, message: str, data: Any | None = None) -> None:
        self.data: Any | None = data
        super().__init__(message)


class UnsatisfyingResultError(CustomError):
    """Error indicating that the result of operation was unsatisfying.

    Useful for API calls where the response was correct, but, for example,
    some conditions were not met.
    """


class RespondWithError(CustomError):
    """Error class for which Error Handler should just send the message back into the context.

    Not an error per se (at least not always), but useful when we have a known exceptional situation
    that requires an early exit but still with a command response.
    """


class PlaceholderError(CustomError):
    """Placeholder Error for "Something went wrong" moments.

    An error type I mostly use for the debugging purposes in places I'm not sure what to do about.
    Can attach some debug data into `.data` attribute for more debugging information.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        self.data: dict[str, Any] = kwargs
        super().__init__(message)


class BadUserInputError(RespondWithError):
    """Error indicating there was a problem with user input."""


class ResponseNotOK(CustomError):  # noqa: N818
    """Raised when `aiohttp`'s session response is not OK.

    Sometimes we just specifically need to raise an error in those cases
    when response from `self.bot.session.get(url)` is not OK.
    I.e. Cache Updates.
    """
