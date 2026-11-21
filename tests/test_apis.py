# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""General tests for the API clients in ``shared.apis``, with a fake HTTP session (no network)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from shared import errors
from shared.apis import dota2com, local, steam_web, stv

if TYPE_CHECKING:
    from .conftest import FakeSession


@pytest.fixture(autouse=True)
def no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Don't wait between retry attempts."""
    monkeypatch.setattr(steam_web.SteamWebAPIClient, "SLEEP_BETWEEN_ATTEMPTS", 0)
    monkeypatch.setattr(dota2com.Dota2comClient, "SLEEP_BETWEEN_ATTEMPTS", 0)


# --- STEAM WEB API ----------------------------------------------------------------------------------------------------


async def test_steam_web_returns_json_and_sends_api_key(session: FakeSession) -> None:
    session.add(json={"result": 1})
    client = steam_web.SteamWebAPIClient(api_key="secret", session=session)  # ty: ignore[invalid-argument-type]
    assert await client._get_json("Some/Endpoint/v1", foo="bar") == {"result": 1}
    _, url, kwargs = session.calls[0]
    assert url == "https://api.steampowered.com/Some/Endpoint/v1"
    assert kwargs["params"] == {"key": "secret", "foo": "bar"}


async def test_steam_web_retries_then_gives_up(session: FakeSession) -> None:
    session.add(status=500, text="oops")
    client = steam_web.SteamWebAPIClient(api_key="secret", session=session)  # ty: ignore[invalid-argument-type]
    with pytest.raises(errors.TooManyFailsError) as exc_info:
        await client._get_json("Some/Endpoint/v1")
    assert len(session.calls) == client.MAX_RETRY_ATTEMPTS
    assert isinstance(exc_info.value.__cause__, errors.ResponseNotOkError)


async def test_steam_web_retries_empty_responses(session: FakeSession) -> None:
    session.add(json={}).add(json={"ok": True})
    client = steam_web.SteamWebAPIClient(api_key="k", session=session)  # ty: ignore[invalid-argument-type]
    assert await client._get_json("Some/Endpoint/v1") == {"ok": True}
    assert len(session.calls) == 2


async def test_steam_web_real_time_stats_needs_server_id(session: FakeSession) -> None:
    client = steam_web.SteamWebAPIClient(api_key="k", session=session)  # ty: ignore[invalid-argument-type]
    with pytest.raises(errors.UnsupportedError):
        await client.get_real_time_stats(None)


# --- DOTA2COM ---------------------------------------------------------------------------------------------------------


async def test_dota2com_hero_list(session: FakeSession) -> None:
    hero = {"id": 1, "name": "npc_dota_hero_antimage", "name_english_loc": "Anti-Mage"}
    session.add(json={"result": {"data": {"heroes": [hero]}}})
    client = dota2com.Dota2comClient(session=session)  # ty: ignore[invalid-argument-type]
    heroes = await client.hero_list()
    assert [(h.id, h.display_name, h.npc_name) for h in heroes] == [(1, "Anti-Mage", "npc_dota_hero_antimage")]


async def test_dota2com_retries_malformed_json(session: FakeSession) -> None:
    session.add(text="<html>not json</html>")
    client = dota2com.Dota2comClient(session=session)  # ty: ignore[invalid-argument-type]
    with pytest.raises(errors.TooManyFailsError):
        await client.item_list()
    assert len(session.calls) == client.MAX_RETRY_ATTEMPTS


# --- LOCAL API --------------------------------------------------------------------------------------------------------


async def test_local_api_parses_response(session: FakeSession) -> None:
    session.add(json={"id": 7, "name": "Irene"})
    client = local.LocalAPI(session, "api-key")  # ty: ignore[invalid-argument-type]
    user = await client.get_steam_user(7)
    assert (user.id, user.name) == (7, "Irene")
    _, url, kwargs = session.calls[0]
    assert url.endswith("/steam_user/7")
    assert kwargs["headers"] == {"X-API-Key": "api-key"}


@pytest.mark.parametrize(
    ("status", "response", "message_part"),
    [
        (401, {"detail": "Unauthorized"}, "API key"),
        (404, {"detail": "Friend not found"}, "Friend not found"),
        (422, {"detail": [{"msg": "bad"}]}, "didn't understand"),
        (500, None, "internal error"),
    ],
)
async def test_local_api_errors_respond_to_user(
    session: FakeSession,
    status: int,
    response: dict[str, object] | None,
    message_part: str,
) -> None:
    if response is None:
        session.add(status=status, text="Internal Server Error")
    else:
        session.add(status=status, json=response)
    client = local.LocalAPI(session, "api-key")  # ty: ignore[invalid-argument-type]
    with pytest.raises(errors.RespondWithError, match=message_part):
        await client.get_friend(1)


# --- 7TV --------------------------------------------------------------------------------------------------------------


def make_stv_client(session: FakeSession) -> stv.StvClient:
    return stv.StvClient(bot_7tv_user_id="bot", bearer_token="token", session=session)  # ty: ignore[invalid-argument-type]


async def test_stv_invoke_returns_data(session: FakeSession) -> None:
    session.add(json={"data": {"emotes": {"emote": {"id": "e1"}}}})
    client = make_stv_client(session)
    assert await client.invoke("query Q { emotes }", {}) == {"emotes": {"emote": {"id": "e1"}}}
    _, _, kwargs = session.calls[0]
    assert kwargs["headers"] == {"Authorization": "Bearer token"}


GQL_ERRORS = [{"message": "BAD_REQUEST emote not found in set", "extensions": {"code": "BAD_REQUEST"}}]


@pytest.mark.parametrize(
    ("status", "payload", "error_cls"),
    [
        (200, {"data": None, "errors": GQL_ERRORS}, stv.InvokeQueryError),
        (200, {"data": {"partial": None}, "errors": GQL_ERRORS}, stv.InvokeQueryError),
        (200, {"status": "Unauthorized", "error_code": 1000}, stv.UnauthorizedError),
        (200, {"something": "else"}, errors.SomethingWentWrongError),
        (503, {"oops": True}, stv.ServiceError),
    ],
)
async def test_stv_invoke_errors(
    session: FakeSession,
    status: int,
    payload: dict[str, object],
    error_cls: type[Exception],
) -> None:
    session.add(status=status, json=payload)
    with pytest.raises(error_cls):
        await make_stv_client(session).invoke("query Q { a }", {})


async def test_stv_owned_session_is_created_lazily_and_closed() -> None:
    client = stv.StvClient(bot_7tv_user_id="bot")  # outside of any request, no session yet
    assert client._session is None
    session = client.session
    assert client.session is session
    await client.close()
    assert session.closed


async def test_stv_does_not_close_foreign_session(session: FakeSession) -> None:
    await make_stv_client(session).close()
    assert not session.closed


def test_stv_cdn_url() -> None:
    emote = stv.PartialEmote(None, "abc")  # ty: ignore[invalid-argument-type]
    assert emote.cdn_url() == "https://cdn.7tv.app/emote/abc/4x.webp"
    assert emote.cdn_url("avif") == "https://cdn.7tv.app/emote/abc/4x.avif"
    assert emote.url() == "7tv.app/emotes/abc"
