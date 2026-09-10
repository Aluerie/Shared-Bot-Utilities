from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NamedTuple, override

from steam import PersonaState
from steam.ext import dota2

from .. import errors
from .api_clients import OpenDotaClient, SteamWebAPIClient, StratzClient

if TYPE_CHECKING:
    from aiohttp import ClientSession

    from ..types_ import database

    class ItemToUpsert(NamedTuple):
        item_id: int
        display_name: str


log = logging.getLogger(__name__)

__all__ = ("Dota2Client",)


class Dota2Client(dota2.Client):
    """Subclass for SteamIO's Client.

    Used to communicate with Dota 2 Game Coordinator in order to track information about my profile real-time.
    """

    def __init__(
        self,
        *,
        session: ClientSession,
        pool: database.PoolTypedWithAny,
        steam_username: str,
        steam_password: str,
        steam_web_api: str,
        stratz_bearer: str,
    ) -> None:
        super().__init__(state=PersonaState.Online)
        self.pool: database.PoolTypedWithAny = pool
        self.started: bool = False
        self.steam_username: str = steam_username
        self.steam_password: str = steam_password

        self.opendota = OpenDotaClient(session=session)
        self.stratz = StratzClient(bearer_token=stratz_bearer, session=session)
        self.web_api = SteamWebAPIClient(api_key=steam_web_api, session=session)

    async def before_login(self) -> None:
        """Before Login.

        This method is supposed to be overwritten by subclasses.
        """

    async def _before_login(self) -> None:
        """Start helping services for steam."""
        if not self.started:
            await self.before_login()
            self.started = True

    @override
    async def login(self, *args: Any, **kwargs: Any) -> None:
        await self._before_login()
        await super().login(self.steam_username, self.steam_password, *args, **kwargs)

    @override
    async def on_ready(self) -> None:
        log.info("🍋 Dota 2 Client: Ready %s, now waiting till Game Coordinator is ready;", self.user.name)
        await self.wait_until_gc_ready()
        log.info("🍋 Dota 2 Game Coordinator: Ready")

    # DATABASE DOTA CONSTANTS

    async def upsert_constants_items(self, to_insert: list[ItemToUpsert], service_name: str) -> None:
        """Upsert data into `dota_constants_items` table."""
        query = """
            INSERT INTO dota_constants_items
            (item_id, display_name)
            VALUES ($1, $2)
            ON CONFLICT (item_id)
                DO UPDATE SET display_name = $2;
        """
        await self.pool.executemany(query, to_insert)
        log.debug("🍋 Database Dota Constants: Updated items with %s API", service_name)

    async def refresh_dota_constants_items(self) -> None:
        """Daily Refresh Database's Dota Constants.

        Notes
        -----
        * IreBot currently only utilizes `dota_constants_items` table.
        * This task first tries to update stuff with Stratz API, if not successful then fallback to OpenDota.
        """
        log.debug("🍋 Database Dota Constants: Refreshing `dota_constants_items`")

        # Stratz
        try:
            items = await self.stratz.get_items()
        except errors.APIDataError as err:
            log.warning("🍋 Stratz API error: `get_items`", exc_info=err)
            # Then we should try with OpenDota
        else:
            await self.upsert_constants_items(
                to_insert=[
                    ItemToUpsert(
                        item_id=item["id"],
                        # Sometimes Stratz return `None` for item display names (hence `or ""`).
                        # Also they put '\x00' into their responses which is not supported by PostgresQL
                        display_name=(item["displayName"] or "").replace("\x00", ""),
                    )
                    for item in items
                ],
                service_name="Stratz",
            )
            return

        # Opendota
        try:
            items = await self.opendota.get_items()
        except errors.APIDataError as err:
            log.warning("🍋 Opendota API error: `get_items`", exc_info=err)
            # Then we are cooked ?
        else:
            await self.upsert_constants_items(
                to_insert=[
                    ItemToUpsert(
                        item_id=item["id"],
                        # Some Opendota items are missing `dname` field.
                        display_name=item.get("dname", ""),
                    )
                    for _key, item in items.items()
                ],
                service_name="Opendota",
            )
            return

        msg = "Something went wrong with `refresh_database_dota_constants`."
        raise errors.PlaceholderError(msg)
