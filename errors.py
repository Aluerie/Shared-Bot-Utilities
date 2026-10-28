"""CUSTOM ERRORS.

All exceptions raised by me should be defined in this file (or subclassed from those).

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
"""

from dataclasses import dataclass
from typing import Any, ClassVar


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
    """The base exception for my projects. All other exceptions should inherit from this."""


class BotError(CustomError):
    """The base exception for my Bot projects. All other exceptions should inherit from this.

    This class introduces various attributes to control whether error handlers should respond to the end-user
    or/and send a notification message to the bot's developers.

    Attributes
    ----------
    policy
        Error handler's desired behavior policy when this error is raised.
    response
        Response message to the end-user. This defaults to the exception message (``str(exc)``).
        Use this attribute to set a different message.
    data
        Extra debug data the error handler attaches to the developer notification.
        This data is only used when `policy.notify` is true.
    default_policy
        Class-level default policy.
    use_fallback_response
        Class-level flag. If true, ``response`` is ignored and the error handler responds with its own fallback message.
    """

    default_policy: ClassVar[Policy] = RESPOND
    use_fallback_response: ClassVar[bool] = False

    def __init__(
        self,
        msg: str,
        *,
        policy: Policy | None = None,
        response: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(msg)
        self.policy: Policy = policy if policy is not None else self.default_policy
        self.response: str = response if response is not None else msg
        self.data: dict[str, Any] = data or {}


########################################################################################################################
# GENERAL ERRORS
########################################################################################################################


class RespondWithError(BotError):
    """Error class for which Error Handler should just send the message back into the context.

    Not an error per se (at least not always), but useful when we have a known exceptional situation
    that requires an early exit but still with a command response.
    """

    default_policy = RESPOND


class RespondAndNotifyError(BotError):
    """Error whose message is shown to the user, and which also notifies developers."""

    default_policy = RESPOND_NOTIFY


class SomethingWentWrongError(RespondAndNotifyError):
    """Placeholder Error for "Something went wrong" situations.

    The end-user response is not set here: error handlers respond with their own
    ``fallback_response``, same as for any non-``BotError`` exception.
    """

    use_fallback_response = True

    def __init__(self, msg: str, *, data: dict[str, Any] | None = None) -> None:
        super().__init__(msg, response="Something went wrong", data=data)


########################################################################################################################
# MORE SPECIFIC ERRORS
########################################################################################################################


class NotAllowedError(BotError):
    """Raised when a user is not allowed to use the requested functionality."""


class BadUserInputError(BotError):
    """Error indicating there was a problem with the user input."""


class UnsupportedError(RespondWithError):
    """UnsupportedError."""


class EmptyResponseError(SomethingWentWrongError):
    """EmptyResponseError."""


class ResponseNotOkError(SomethingWentWrongError):
    """ResponseNotOkError."""


class TooManyFailsError(SomethingWentWrongError):
    """TooManyFailsError."""
