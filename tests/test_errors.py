# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Tests for ``shared.errors`` and how ``BotBase`` responds according to their policies."""

import pytest

from shared import errors
from shared.concepts import BotBase


def test_bot_error_defaults() -> None:
    error = errors.BotError("boom")
    assert str(error) == "boom"
    assert error.response == "boom"
    assert error.policy == errors.RESPOND
    assert error.data == {}


def test_bot_error_overrides() -> None:
    error = errors.BotError("internal", policy=errors.SILENT, response="public", data={"x": 1})
    assert error.policy == errors.SILENT
    assert error.response == "public"
    assert error.data == {"x": 1}


@pytest.mark.parametrize(
    ("error_cls", "policy"),
    [
        (errors.RespondWithError, errors.RESPOND),
        (errors.RespondAndNotifyError, errors.RESPOND_NOTIFY),
        (errors.SomethingWentWrongError, errors.RESPOND_NOTIFY),
        (errors.UnsupportedError, errors.RESPOND),
        (errors.TooManyFailsError, errors.RESPOND_NOTIFY),
    ],
)
def test_default_policies(error_cls: type[errors.BotError], policy: errors.Policy) -> None:
    assert error_cls("msg").policy == policy
    assert issubclass(error_cls, errors.CustomError)


class FakeBot:
    """Only what ``BotBase.respond_per_policy`` needs, without webhooks or sessions."""

    SOMETHING_WENT_WRONG_MESSAGE = BotBase.SOMETHING_WENT_WRONG_MESSAGE
    respond_per_policy = BotBase.respond_per_policy


@pytest.mark.parametrize(
    ("error", "expected_response", "expected_notify"),
    [
        (errors.RespondWithError("Try again"), "Try again", False),
        (errors.RespondAndNotifyError("Oops"), "Oops", True),
        (errors.SomethingWentWrongError("details for devs"), "Something went wrong", True),
        (errors.BotError("quiet", policy=errors.SILENT), None, False),
        (ValueError("unexpected"), "Something went wrong", True),
    ],
)
async def test_respond_per_policy(
    error: Exception,
    expected_response: str | None,
    expected_notify: bool,  # ruff: ignore[boolean-type-hint-positional-argument]
) -> None:
    responses: list[str] = []

    async def respond(text: str) -> None:
        responses.append(text)

    notify = await FakeBot().respond_per_policy(error, respond)
    assert notify is expected_notify
    assert responses == ([expected_response] if expected_response is not None else [])


async def test_respond_per_policy_survives_failing_respond() -> None:
    async def respond(_: str) -> None:
        msg = "channel is gone"
        raise RuntimeError(msg)

    assert await FakeBot().respond_per_policy(errors.RespondAndNotifyError("x"), respond) is True
