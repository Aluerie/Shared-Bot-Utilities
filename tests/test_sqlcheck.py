# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Tests for checking a bot's SQL against its migrations.

The database test runs only when the ``SHARED_TEST_POSTGRES`` environment variable holds a connection string.
"""

import os
from pathlib import Path

import asyncpg
import pytest

from shared.sqlcheck import Query, find_queries, prepare_all

DSN = os.environ.get("SHARED_TEST_POSTGRES")

SOURCE = '''
"""SELECT in a module docstring doesn't count FROM anywhere."""

QUERY = """
    SELECT id, name
    FROM things
"""


async def handler(pool, table):
    await pool.execute("UPDATE things SET name = $1 WHERE id = $2", "x", 1)
    await pool.fetch(f"SELECT id FROM {table}")
    await ctx.send("Select a hero from the list")  # UI text, not SQL
'''


def write_source(tmp_path: Path) -> Path:
    source = tmp_path / "src"
    (source / "ext").mkdir(parents=True)
    (source / "ext" / "things.py").write_text(SOURCE, encoding="utf-8")
    (source / "shared").mkdir()
    (source / "shared" / "skipped.py").write_text('QUERY = "SELECT * FROM elsewhere"\n', encoding="utf-8")
    return source


def test_find_queries_collects_literals_and_fstrings_separately(tmp_path: Path) -> None:
    literals, fstrings = find_queries(write_source(tmp_path))

    assert [(q.location, q.sql.split()[0]) for q in literals] == [
        ("ext/things.py:4", "SELECT"),
        ("ext/things.py:11", "UPDATE"),
    ]
    assert [q.location for q in fstrings] == ["ext/things.py:12"]


def test_find_queries_can_include_excluded_folders(tmp_path: Path) -> None:
    literals, _ = find_queries(write_source(tmp_path), exclude=())
    assert "shared/skipped.py:1" in [q.location for q in literals]


@pytest.mark.skipif(DSN is None, reason="SHARED_TEST_POSTGRES is not set")
async def test_prepare_all_reports_only_the_broken_queries(tmp_path: Path) -> None:
    assert DSN is not None
    folder = tmp_path / "migrations"
    folder.mkdir()
    (folder / "0001_baseline.sql").write_text(
        "CREATE TABLE app.things (id INTEGER PRIMARY KEY, name TEXT);", encoding="utf-8"
    )
    good = Query(Path("ok.py"), 1, "SELECT id, name FROM things WHERE id = $1")
    from_setup = Query(Path("setup.py"), 1, "SELECT kind FROM jobs")
    bad_column = Query(Path("bad.py"), 2, "SELECT colour FROM things")
    bad_table = Query(Path("bad.py"), 3, "DELETE FROM no_such_table")

    failures = await prepare_all(
        DSN,
        [good, from_setup, bad_column, bad_table],
        search_path="app",
        migration_dirs=[("app", folder)],
        setup_sql=["CREATE TABLE jobs (kind TEXT)"],
    )

    assert [(query, error.split(":")[0]) for query, error in failures] == [
        (bad_column, "UndefinedColumnError"),
        (bad_table, "UndefinedTableError"),
    ]
    admin = await asyncpg.connect(DSN)
    try:
        leftovers = await admin.fetchval("SELECT count(*) FROM pg_database WHERE datname LIKE 'sqlcheck\\_%'")
    finally:
        await admin.close()
    assert leftovers == 0
