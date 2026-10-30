# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Database."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any, cast, override

import asyncpg
import click
import orjson


async def create_pool(postgres_url: str, search_path: str) -> PoolTypedWithAny:
    """Create a database connection pool.

    Parameters
    ----------
    postgres_url: str
        Postgresql URL to use for connection.
    search_path: str
        Search path for `asyncpg.create_pool`'s server_settings.
    """

    async def init(con: asyncpg.Connection[asyncpg.Record]) -> None:
        def _encode_jsonb(value: Any) -> str:
            return orjson.dumps(value).decode("utf-8")

        def _decode_jsonb(value: str) -> Any:
            return orjson.loads(value)

        await con.set_type_codec(
            typename="jsonb",
            schema="pg_catalog",
            encoder=_encode_jsonb,
            decoder=_decode_jsonb,
            format="text",
        )

    return cast(
        "PoolTypedWithAny",
        await asyncpg.create_pool(
            dsn=postgres_url,
            init=init,
            command_timeout=300,
            min_size=20,
            max_size=20,
            # statement_cache_size=0,
            server_settings={"search_path": search_path},
        ),
    )


if TYPE_CHECKING:

    class PoolTypedWithAny(asyncpg.Pool[asyncpg.Record]):
        """Fake Type Class.

        For typing purposes, our `bot.pool` will be "type-ignore"'d-as `PoolTypedWithAny`
        that allows us to properly type the return values via narrowing
        without hundreds of "ty: ignore" notices for each TypedDict.

        I could use Protocol to type it all, but `async-stubs` provide a good job in typing most of the stuff
        and we also don't lose doc-string this way.

        * Right now, asyncpg is untyped so this is better than the current status quo
        * If we ever need the regular Pool type we can make `bot.database` without the type-hint.
        """

        # all methods below were changed from "asyncpg.Record" to "Any"

        @override
        async def fetch(self, query: str, *args: Any, timeout: float | None = None) -> list[Any]: ...  # ty: ignore[invalid-method-override]

        @override
        async def fetchrow(self, query: str, *args: Any, timeout: float | None = None) -> Any: ...  # ty: ignore[invalid-method-override]


async def try_create_pool(
    postgres_prod: str,
    postgres_test: str,
    *,
    search_path: str,
    is_test: bool,
) -> PoolTypedWithAny:
    """Create a database connection pool but with error handling."""
    log = logging.getLogger(__name__)
    postgres_url = postgres_test if is_test else postgres_prod
    try:
        return await create_pool(postgres_url, search_path)
    except Exception:
        msg = "Could not set up PostgreSQL. Exiting."
        # error message to terminal
        click.echo(msg, file=sys.stderr)
        # error message to logs
        log.exception(msg)
        sys.exit(1)
