"""CUSTOM ERRORS.

All exceptions raised by me should be defined in this file.
It's just my small code practice.
It might be a little bit overthinking, but it gets the job done the way I want.

Notes
-----
Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Final

SOMETHING_WENT_WRONG_MESSAGE: Final = "Something went wrong; Irene has been notified about this"


@dataclass(frozen=True, slots=True)
class Policy:
    """Class defining behavior policy for error handlers.

    Attributes
    ----------
    respond
        Whether the bot should respond to end-user.
    notify
        Whether the bot should notify its developers about the raised exception.
    """

    respond: bool
    notify: bool


SILENT = Policy(respond=False, notify=False)
RESPOND = Policy(respond=True, notify=False)
RESPOND_NOTIFY = Policy(respond=True, notify=True)


class CustomError(Exception):
    """The base exception for my (@Aluerie) projects. All other exceptions should inherit from this."""


class BotError(CustomError):
    """The base exception for my (@Aluerie) Bot projects. All other exceptions should inherit from this.

    This class introduces various attributes to control whether error handlers should respond to the end-user or/and send
    a notification message to the bot's developers.

    Attributes
    ----------
    policy
        Error handler's desired behavior policy when this error is raised.
    response_msg
        Response message to the end-user. This defaults to the exception message (``str(exc)``).
        Use this attribute to set a different message.
    data
        Extra debug data the error handler attaches to the developer notification.
        This data is only used when `policy.notify` is true.
    """

    default_policy: ClassVar[Policy] = RESPOND

    def __init__(
        self,
        msg: str,
        *,
        policy: Policy | None = None,
        response_msg: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(msg)
        self.policy: Policy = policy if policy is not None else self.default_policy
        self.response_msg: str = response_msg or msg
        self.data: dict[str, Any] = data or {}


#############################################################################################################################
# GENERAL ERRORS
#############################################################################################################################


class RespondWithError(BotError):
    """Error class for which Error Handler should just send the message back into the context.

    Not an error per se (at least not always), but useful when we have a known exceptional situation
    that requires an early exit but still with a command response.
    """


class RespondAndNotifyError(BotError):
    """Error whose message is shown to the user, and which also notifies developers."""

    default_policy = RESPOND_NOTIFY


class SomethingWentWrongError(RespondAndNotifyError):
    """Placeholder Error for "Something went wrong" situations.

    Error I mostly use for the debugging purposes in places I'm not sure what to do about.
    """

    def __init__(self, msg: str, *, data: dict[str, Any] | None = None) -> None:
        super().__init__(msg, response_msg=SOMETHING_WENT_WRONG_MESSAGE, data=data)


#############################################################################################################################
# MORE SPECIFIC ERRORS
#############################################################################################################################


class NotAllowedError(BotError):
    """Raised when a user is not allowed to use the requested functionality."""


class BadUserInputError(BotError):
    """Error indicating there was a problem with the user input."""


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


class ApiError(CustomError):
    """Api Error.

    This error is raised when there is a problem with a 3rd party API.

    Attributes
    ----------
    data: Any | None
        Data that API attached to the response, if any.

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
