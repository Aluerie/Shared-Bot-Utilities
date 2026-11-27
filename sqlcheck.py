# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Check a bot's SQL against the schema its migrations build, without running any of it.

`find_queries` collects the SQL string literals in a bot's source. `prepare_all` builds a throwaway database from
migration folders and asks PostgreSQL to prepare every query there, which checks every table, column, function
and type the query uses. A query that fails here would fail the same way at runtime.

Queries built with f-strings can't be checked, since they're only complete at runtime; `find_queries` lists them
separately so that a test can mention them.
"""

from __future__ import annotations

import ast
import re
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

import asyncpg

from .concepts import migrations

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

__all__ = ("Query", "find_queries", "prepare_all")

# Uppercase keywords only, so user-facing text like "Select a hero from the list" doesn't count as SQL.
SQL_START = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|WITH)\b")
SQL_SHAPE = re.compile(r"\b(FROM|INTO|SET|RETURNING|VALUES)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Query:
    """An SQL string found in the source."""

    path: Path
    line: int
    sql: str

    @property
    def location(self) -> str:
        """``path:line``, for messages."""
        return f"{self.path.as_posix()}:{self.line}"


def _looks_like_sql(text: str) -> bool:
    return SQL_START.match(text) is not None and SQL_SHAPE.search(text) is not None


def _docstring_ids(tree: ast.Module) -> set[int]:
    nodes = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, nodes)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }


def find_queries(source: Path, *, exclude: Iterable[str] = ("shared",)) -> tuple[list[Query], list[Query]]:
    """Find the SQL in the ``.py`` files under ``source``: string literals and f-strings, as two lists.

    A string counts as SQL when it starts with an uppercase ``SELECT``, ``INSERT``, ``UPDATE``, ``DELETE`` or ``WITH``
    and contains ``FROM``, ``INTO``, ``SET``, ``RETURNING`` or ``VALUES``. Docstrings never count. Folders named in
    ``exclude`` are skipped (by default the ``shared`` submodule, whose own CI checks its SQL). For f-strings,
    ``Query.sql`` holds only their literal parts.
    """
    excluded = set(exclude)
    literals: list[Query] = []
    fstrings: list[Query] = []
    for path in sorted(source.rglob("*.py")):
        relative = path.relative_to(source)
        if excluded.intersection(relative.parts[:-1]):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        # docstrings and the literal pieces of f-strings are string constants too, but not queries of their own
        skipped = _docstring_ids(tree) | {
            id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skipped:
                if _looks_like_sql(node.value):
                    literals.append(Query(relative, node.lineno, node.value))
            elif isinstance(node, ast.JoinedStr):
                text = "".join(str(part.value) for part in node.values if isinstance(part, ast.Constant))
                if _looks_like_sql(text):
                    fstrings.append(Query(relative, node.lineno, text))
    return literals, fstrings


async def prepare_all(
    dsn: str,
    queries: Iterable[Query],
    *,
    search_path: str,
    migration_dirs: Iterable[tuple[str, Path]],
    setup_sql: Iterable[str] = (),
) -> list[tuple[Query, str]]:
    """Prepare every query in a throwaway database and return the ones that failed, with PostgreSQL's error.

    Parameters
    ----------
    dsn
        A connection string for a user who may create databases. The throwaway database is created next to the one
        it names, and dropped at the end.
    queries
        The queries to check, e.g. the first list from `find_queries`.
    search_path
        The ``search_path`` the bot's pool uses, so unqualified table names resolve the same way.
    migration_dirs
        ``(schema, folder)`` pairs, applied in order. Schemas that reference others come after them.
    setup_sql
        More SQL to run after the migrations, with ``search_path`` set, e.g. the scheduler's ``schema.sql``.
    """
    name = f"sqlcheck_{secrets.token_hex(4)}"
    admin = await asyncpg.connect(dsn)
    await admin.execute(f"CREATE DATABASE {name}")
    try:
        for schema, directory in migration_dirs:
            pool = await asyncpg.create_pool(
                dsn, database=name, min_size=1, max_size=1, server_settings={"search_path": schema}
            )
            try:
                await migrations.apply(pool, directory, schema=schema)
            finally:
                await pool.close()

        connection = await asyncpg.connect(dsn, database=name, server_settings={"search_path": search_path})
        try:
            for sql in setup_sql:
                await connection.execute(sql)
            failures: list[tuple[Query, str]] = []
            for query in queries:
                try:
                    await connection.prepare(query.sql)
                except asyncpg.PostgresError as error:
                    failures.append((query, f"{type(error).__name__}: {error}"))
            return failures
        finally:
            await connection.close()
    finally:
        await admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        await admin.close()
