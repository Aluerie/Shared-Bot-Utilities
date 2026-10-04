"""CUSTOM ERRORS.

All exceptions raised by me should be defined in this file.
It's just my small code practice.


Notes
-----
The following errors are used as special means to notify the chatters about the error.
Their type depends on whether the developers should also be notified.
|                           | User notified?                       | Devs notified? |
| ------------------------- | ------------------------------------ | -------------- |
| SilentError               | No                                   | No             |
| RespondWithError          | Yes                                  | No             |
| RespondAndNotifyDevsError | Yes                                  | Yes            |
| SomethingWentWrongError   | Yes, but with 'Something Went Wrong' | Yes            |
| Other Exception Types     | Depends - look into Error Handlers   | Depends        |

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

from typing import Any


class CustomError(Exception):
    """The base exception for my (@Aluerie) projects. All other exceptions should inherit from this."""


class BotError(CustomError):
    """The base exception for my (@Aluerie) Bot projects. All other exceptions should inherit from this.

    Due to the bots' nature of interacting with - it needs to interact with its users.
    Exactly for this purpose, this class has various attributes that control how error handlers are supposed
    to handle such exceptions.

    Attributes
    ----------
    msg: str
        Message to initiate the exception with.
    respond: bool = True
        Whether the bot should respond in twitch chat.
    something_went_wrong: bool = False
        Whether to use `msg` as a response or prepared "Oups, something went wrong" message.
        Useful for when we want to hide the error from the user.
    silent: bool = False
        Whether the bot's error handlers should silently ignore this error.
        If this flag is True then the bot won't care about any other attributes - just silence.
    register: bool = False
        Whether a notification with a full report for the developers about the error should be registered.
        These reports are sent in my private discord so I can look at them in a great detail.
    **debug_data_kwargs: Any
        If any are provided - the bot will attach this data to the mentioned above message for the developers.
    """

    def __init__(
        self,
        msg: str,
        *,
        respond: bool = True,
        something_went_wrong: bool = False,
        silent: bool = False,
        register: bool = False,
        **debug_data_kwargs: Any,
    ) -> None:
        super().__init__(msg)
        self.msg: str = msg
        self.respond: bool = respond
        self.something_went_wrong: bool = something_went_wrong
        self.silent: bool = silent
        self.register: bool = register
        self.debug_data: dict[str, Any] = debug_data_kwargs


class NotAllowedError(BotError):
    """Raised when a user is not allowed to use the requested functionality."""


class BadUserInputError(BotError):
    """Error indicating there was a problem with the user input."""


class RespondWithError(BotError):
    """Error class for which Error Handler should just send the message back into the context.

    Not an error per se (at least not always), but useful when we have a known exceptional situation
    that requires an early exit but still with a command response.
    """


class SomethingWentWrongError(BotError):
    """Placeholder Error for "Something went wrong" moments.

    An error type I mostly use for the debugging purposes in places I'm not sure what to do about.
    Can attach some debug data into `.data` attribute for more debugging information.
    """

    def __init__(self, msg: str, **debug_data_kwargs: Any) -> None:
        super().__init__(msg, something_went_wrong=True, register=True, **debug_data_kwargs)


########################################
# ERRORS CONTROLLING RESPONSE BEHAVIOR #
########################################


# class SilentError(CustomError):
#     """Errors to be ignored by error handlers."""


# class RespondWithError(CustomError):
#     """Error class for which Error Handler should just send the message back into the context.

#     Not an error per se (at least not always), but useful when we have a known exceptional situation
#     that requires an early exit but still with a command response.
#     """


# class RespondAndNotifyDevsError(CustomError):
#     """."""

#     def __init__(self, msg: str, for_devs: str | None = None, **kwargs: Any) -> None:
#         self.for_devs: str = for_devs or msg
#         self.debug_data: dict[str, Any] = kwargs
#         super().__init__(msg)


# class SomethingWentWrongError(CustomError):
#     """Placeholder Error for "Something went wrong" moments.

#     An error type I mostly use for the debugging purposes in places I'm not sure what to do about.
#     Can attach some debug data into `.data` attribute for more debugging information.
#     """

#     def __init__(self, msg: str, **kwargs: Any) -> None:
#         self.debug_data: dict[str, Any] = kwargs
#         super().__init__(msg)


# ########################################
# # Other #
# ########################################


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


# class UnsatisfyingResultError(CustomError):
#     """Error indicating that the result of operation was unsatisfying.

#     Useful for API calls where the response was correct, but, for example,
#     some conditions were not met.
#     """


# class BadUserInputError(RespondWithError):
#     """Error indicating there was a problem with user input."""


# class ResponseNotOK(CustomError):
#     """Raised when `aiohttp`'s session response is not OK.

#     Sometimes we just specifically need to raise an error in those cases
#     when response from `self.bot.session.get(url)` is not OK.
#     I.e. Cache Updates.
#     """
