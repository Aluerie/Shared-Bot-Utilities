from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

import asyncpg
import orjson


async def create_pool(postgres_url: str) -> asyncpg.Pool[asyncpg.Record]:
    """Create a database connection pool.

    Parameters
    ----------
    postgres_url: str
        Postgresql URL to use for connection.
    """

    def _encode_jsonb(value: Any) -> str:
        return orjson.dumps(value).decode("utf-8")

    def _decode_jsonb(value: str) -> Any:
        return orjson.loads(value)

    async def init(con: asyncpg.Connection[asyncpg.Record]) -> None:
        await con.set_type_codec(
            typename="jsonb",
            schema="pg_catalog",
            encoder=_encode_jsonb,
            decoder=_decode_jsonb,
            format="text",
        )

    return await asyncpg.create_pool(
        postgres_url,
        init=init,
        command_timeout=300,
        min_size=20,
        max_size=20,
        # statement_cache_size=0,
    )


if TYPE_CHECKING:

    class PoolTypedWithAny(asyncpg.Pool[asyncpg.Record]):
        """Fake Type Class.

        For typing purposes, our `bot.pool` will be "type-ignore"'d-as `PoolTypedWithAny`
        that allows us to properly type the return values via narrowing like mentioned in instructions above
        without hundreds of "pyright: ignore" notices for each TypedDict.

        I could use Protocol to type it all, but `async-stubs` provide a good job in typing most of the stuff
        and we also don't lose doc-string this way.

        * Right now, asyncpg is untyped so this is better than the current status quo
        * If we ever need the regular Pool type we have `bot.database` without any shenanigans.
        """

        # all methods below were changed from "asyncpg.Record" to "Any"

        @override
        async def fetch(self, query: str, *args: Any, timeout: float | None = None) -> list[Any]: ...  # pyright: ignore[reportIncompatibleMethodOverride]

        @override
        async def fetchrow(self, query: str, *args: Any, timeout: float | None = None) -> Any: ...  # pyright: ignore[reportIncompatibleMethodOverride]
