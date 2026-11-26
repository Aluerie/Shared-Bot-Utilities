# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
# ruff: file-ignore[hardcoded-sql-expression]  # the only interpolated name is the schema, checked against IDENTIFIER
"""Database migrations: numbered SQL files, applied once each, in order, when the bot starts.

A bot keeps its files in a ``migrations/`` folder, named ``NNNN_description.sql`` (``0001_baseline.sql``,
``0002_fix_blacklist_fkey.sql``, ...). Each file runs in its own transaction, together with the row in
``<schema>.schema_migrations`` that records it, so a file either applies completely or not at all.
A file must not contain ``BEGIN``/``COMMIT`` or statements that can't run in a transaction
(e.g. ``CREATE INDEX CONCURRENTLY``).

Applied files must never change: a new change is a new file. Changing an applied file only logs a warning.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from pathlib import Path

    import asyncpg
    from asyncpg.pool import PoolConnectionProxy

__all__ = ("Migration", "MigrationError", "apply", "load")

FILE_NAME = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")
IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
BASELINE_NAME = "baseline"


class MigrationError(Exception):
    """A migrations folder or schema that can't be migrated."""


@dataclass(frozen=True, slots=True)
class Migration:
    """One migration file."""

    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        """SHA-256 of the file's text, with line endings normalized so checkouts on any OS agree."""
        return hashlib.sha256(self.sql.replace("\r\n", "\n").encode()).hexdigest()

    @property
    def file_name(self) -> str:
        """The file's name, e.g. ``0001_baseline.sql``."""
        return f"{self.version:04d}_{self.name}.sql"


def load(directory: Path) -> list[Migration]:
    """Read the migration files of a folder, sorted by version.

    Raises
    ------
    MigrationError
        The folder is missing, a ``.sql`` file is named wrongly, or two files share a version.
    """
    if not directory.is_dir():
        msg = f"Migrations folder {directory} doesn't exist."
        raise MigrationError(msg)
    migrations: dict[int, Migration] = {}
    for path in sorted(directory.glob("*.sql")):
        match = FILE_NAME.match(path.name)
        if match is None:
            msg = f"Migration file {path.name} isn't named like 0001_description.sql."
            raise MigrationError(msg)
        version = int(match["version"])
        if version in migrations:
            msg = f"Migration files {migrations[version].file_name} and {path.name} share version {version}."
            raise MigrationError(msg)
        migrations[version] = Migration(version, match["name"], path.read_text(encoding="utf-8"))
    return [migrations[version] for version in sorted(migrations)]


async def apply(pool: asyncpg.Pool[Any], directory: Path, *, schema: str) -> list[Migration]:
    """Apply the migrations of ``directory`` that ``schema`` doesn't have yet, and return them.

    Creates ``schema`` and its ``schema_migrations`` table if they don't exist. When the table is new but the schema
    already holds tables (a database from before migrations), a first migration named ``baseline`` is recorded
    as applied without running, since the database already is what it describes.

    An advisory lock keeps two processes from migrating the same schema at the same time.
    When a migration fails, its error propagates: that migration is rolled back, and the later ones don't run.

    Raises
    ------
    MigrationError
        The folder is missing or has a wrongly named or duplicate file,
        or ``schema`` isn't a plain lowercase identifier.
    """
    if IDENTIFIER.match(schema) is None:
        msg = f"Schema name {schema!r} must be a plain lowercase identifier."
        raise MigrationError(msg)
    migrations = load(directory)
    lock_key = f"migrations:{schema}"

    async with pool.acquire() as connection:
        await connection.execute("SELECT pg_advisory_lock(hashtext($1))", lock_key)
        try:
            await _prepare(connection, schema, migrations)
            applied: dict[int, str] = {
                row["version"]: row["checksum"]
                for row in await connection.fetch(f"SELECT version, checksum FROM {schema}.schema_migrations")
            }
            _warn_about_mismatches(schema, migrations, applied)

            new = [migration for migration in migrations if migration.version not in applied]
            for migration in new:
                async with connection.transaction():
                    await connection.execute(migration.sql)
                    await connection.execute(
                        f"INSERT INTO {schema}.schema_migrations (version, name, checksum) VALUES ($1, $2, $3)",
                        migration.version,
                        migration.name,
                        migration.checksum,
                    )
                logger.info("Migrations: applied {} to schema {}.", migration.file_name, schema)
            return new
        finally:
            await connection.execute("SELECT pg_advisory_unlock(hashtext($1))", lock_key)


async def _prepare(connection: PoolConnectionProxy[Any], schema: str, migrations: list[Migration]) -> None:
    """Create the schema and its ``schema_migrations`` table, recording the baseline of a pre-migrations schema."""
    async with connection.transaction():
        await connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        table_exists = await connection.fetchval("SELECT to_regclass($1) IS NOT NULL", f"{schema}.schema_migrations")
        if table_exists:
            return
        await connection.execute(
            f"""
            CREATE TABLE {schema}.schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        has_tables = await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_tables WHERE schemaname = $1 AND tablename <> 'schema_migrations'
            )
            """,
            schema,
        )
        if has_tables and migrations and migrations[0].name == BASELINE_NAME:
            baseline = migrations[0]
            await connection.execute(
                f"INSERT INTO {schema}.schema_migrations (version, name, checksum) VALUES ($1, $2, $3)",
                baseline.version,
                baseline.name,
                baseline.checksum,
            )
            logger.warning(
                "Migrations: schema {} already has tables, so {} is recorded as applied without running it.",
                schema,
                baseline.file_name,
            )


def _warn_about_mismatches(schema: str, migrations: list[Migration], applied: dict[int, str]) -> None:
    """Log applied migrations whose file changed since, or that have no file (e.g. older code was deployed)."""
    files = {migration.version: migration for migration in migrations}
    for version, checksum in sorted(applied.items()):
        migration = files.get(version)
        if migration is None:
            logger.warning(
                "Migrations: schema {} has version {:04d} applied, but there's no file for it.", schema, version
            )
        elif migration.checksum != checksum:
            logger.warning(
                "Migrations: {} changed after it was applied to schema {}. Put changes into a new file instead.",
                migration.file_name,
                schema,
            )
