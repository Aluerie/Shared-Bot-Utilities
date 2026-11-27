# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Scheduler: runs jobs from the ``scheduled_jobs`` table at their time, across restarts.

How it works
------------
* Every `poll_interval` the scheduler claims the jobs that are due within the look-ahead window
  (``UPDATE ... SET claimed_at ... RETURNING``) and starts a task for each that sleeps until the job's exact moment.
  Scheduling or changing a job wakes the loop right away, so short jobs don't wait for the next poll.
* When a job fires, its kind's handler runs. Returning normally finishes the occurrence: one-off jobs are deleted,
  repeating jobs move to their next occurrence. Raising retries the occurrence with a growing delay,
  then gives up on it. Handlers never clean up after themselves.
* Jobs are delivered at least once: a job claimed by a process that died before finishing it
  is released (and runs again) when the scheduler starts.

The scheduler expects to be the only one running jobs from its table (one process per bot).
"""

import asyncio
import contextlib
import dataclasses
import datetime as dt
import enum
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, Literal, override
lazy import traceback

import asyncpg
from loguru import logger

from . import recurrence
from .jobs import HANDLER_ATTRIBUTE, STOP, HandlerSpec, Job, JobData, JobRun, Outcome, Reschedule
from .walltime import UTC, WallTime, When, to_wall_time

__all__ = (
    "UNSET",
    "JobExistsError",
    "OnConflict",
    "Scheduler",
)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

COLUMNS = "*, (local_due AT TIME ZONE timezone) AS due_at"
FIRE_AT = "COALESCE(retry_at, local_due AT TIME ZONE timezone)"
"""SQL expression of the moment a job fires."""

MIN_LOOP_RETRY = 5.0
MAX_LOOP_RETRY = 300.0
"""Bounds (in seconds) of the poll loop's back-off while the database is unavailable."""
UNKNOWN_KINDS_CHECK_INTERVAL = dt.timedelta(hours=1)
UNKNOWN_KINDS_GRACE = dt.timedelta(hours=1)
"""Jobs this overdue whose kind has no handler get a warning in the logs (a typo or a cog that isn't loaded)."""
HISTORY_DAYS = 90
"""Rows of `scheduled_job_runs` are kept this many days (pruned with the hourly unknown-kinds check)."""
NOTIFY_CHANNEL = "scheduled_jobs"
"""PostgreSQL channel that `schema.sql`'s trigger notifies, with the table's schema as the payload."""

type OnConflict = Literal["error", "replace", "keep"]
"""What `Scheduler.schedule` does when a job with the same key exists: raise, replace it or keep it."""
type ErrorCallback = Callable[[BaseException, Job | None], Awaitable[object]]
"""Called with errors of handlers (and the job) and of the scheduler itself (job `None`)."""
type Clock = Callable[[], dt.datetime]
"""Returns the current moment as an aware datetime."""


class JobExistsError(Exception):
    """A job with the given key already exists.

    Attributes
    ----------
    key
        The key of the existing job.
    """

    def __init__(self, key: str) -> None:
        super().__init__(f"A job with the key {key!r} already exists.")
        self.key: str = key


class _Unset(enum.Enum):
    UNSET = enum.auto()


UNSET = _Unset.UNSET


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _json(data: JobData | None) -> dict[str, Any]:
    # `Job.data` is a `frozendict`, which the JSON encoder doesn't know about
    return dict(data or {})


class Scheduler:
    """Runs jobs from the ``scheduled_jobs`` table at their time.

    Parameters
    ----------
    pool
        Database pool. The table lives in the first schema of its ``search_path``.
    poll_interval
        How often the database is polled for due jobs. Jobs still fire on time:
        they are claimed ahead (twice the interval) and wait in memory for their exact moment.
    clock
        Returns the current moment. Only tests need anything else.
    on_error
        Coroutine function called with handler errors (and the job) and scheduler errors (job `None`).
        Errors are logged either way.
    max_concurrency
        How many handlers may run at the same time. After downtime many jobs are due at once;
        the rest wait for a free slot instead of all hitting Discord's (or Twitch's) rate limits together.
    """

    def __init__(
        self,
        pool: asyncpg.Pool[Any],
        *,
        poll_interval: dt.timedelta = dt.timedelta(seconds=30),
        clock: Clock = _utcnow,
        on_error: ErrorCallback | None = None,
        max_concurrency: int = 5,
    ) -> None:
        self.pool: asyncpg.Pool[Any] = pool
        self.poll_interval: dt.timedelta = poll_interval
        self.lookahead: dt.timedelta = poll_interval * 2
        self.clock: Clock = clock
        self._on_error: ErrorCallback | None = on_error
        self._slots: asyncio.Semaphore = asyncio.Semaphore(max_concurrency)
        self._schema: str | None = None
        """The schema of the table, which `NOTIFY`s carry; known after `start`."""
        self._listener: Any = None
        """The pool connection held for `LISTEN`, while it's alive."""

        self._handlers: dict[str, HandlerSpec] = {}
        self._pending: dict[int, tuple[Job, asyncio.Task[None]]] = {}
        """Claimed jobs whose tasks are sleeping until their moment. Cancelling these is safe."""
        self._running: dict[int, asyncio.Task[None]] = {}
        """Jobs whose handlers are running. These are never cancelled, except on shutdown."""
        self._wake: asyncio.Event = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None
        self._closing: bool = False
        self._warned_kinds: set[str] = set()
        self._unknown_kinds_checked_at: dt.datetime | None = None
        self._background_tasks: set[asyncio.Task[None]] = set()
        """Strong references to fire-and-forget tasks, so they aren't garbage collected midway."""

    # --- LIFECYCLE ----------------------------------------------------------------------------------------------------

    async def install(self) -> None:
        """Create the table (if it doesn't exist) in the first schema of the pool's ``search_path``."""
        await self.pool.execute(SCHEMA_PATH.read_text(encoding="utf-8"))

    async def start(self, *, wait_until: Callable[[], Awaitable[object]] | None = None, install: bool = True) -> None:
        """Start running jobs.

        Jobs that a previous process claimed but didn't finish are released, so they run again.

        Parameters
        ----------
        wait_until
            Coroutine function to await before the first job runs, e.g. the bot's ``wait_until_ready``,
            so handlers find a filled cache.
        install
            Whether to create the table if it doesn't exist.
        """
        if self._loop_task is not None:
            msg = "The scheduler is already started."
            raise RuntimeError(msg)
        if install:
            await self.install()
        self._schema = await self.pool.fetchval("SELECT current_schema()")
        released = await self.pool.execute("UPDATE scheduled_jobs SET claimed_at = NULL WHERE claimed_at IS NOT NULL")
        if released != "UPDATE 0":
            logger.info("Scheduler: released unfinished jobs of the previous run ({}).", released)
        self._loop_task = asyncio.create_task(self._run(wait_until), name="scheduler-loop")

    async def close(self, *, grace_period: float = 8.0) -> None:
        """Stop running jobs.

        Jobs waiting for their moment are released at once. Running handlers get `grace_period` seconds to finish;
        the ones that don't are cancelled and run again after the next start.

        Parameters
        ----------
        grace_period
            Seconds to wait for running handlers. Keep it under the time the process manager waits
            before killing the process (10 seconds for ``docker stop``, 90 for systemd by default).
        """
        self._closing = True
        if self._loop_task is not None:
            self._loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._loop_task
        await self._drop_listener()

        pending = list(self._pending.items())
        self._pending.clear()
        for _, task in (value for _, value in pending):
            task.cancel()
        if pending:
            try:
                await self._release([job_id for job_id, _ in pending])
            except Exception:  # ruff: ignore[blind-except]
                logger.opt(exception=True).warning("Scheduler: could not release waiting jobs on close.")

        if running := list(self._running.values()):
            _, unfinished = await asyncio.wait(running, timeout=grace_period)
            for task in unfinished:
                task.cancel()
            if unfinished:
                logger.warning("Scheduler: cancelled {} unfinished handlers on close.", len(unfinished))

    # --- HANDLERS -----------------------------------------------------------------------------------------------------

    def register(self, spec: HandlerSpec) -> None:
        """Register a handler for a kind of jobs.

        Jobs of a kind without a handler wait in the table until one is registered.

        Raises
        ------
        ValueError
            If the kind already has a different handler.
        """
        existing = self._handlers.get(spec.kind)
        if existing is not None and existing.func != spec.func:
            msg = f"The kind {spec.kind!r} already has a handler: {existing.func!r}."
            raise ValueError(msg)
        self._handlers[spec.kind] = spec
        self._warned_kinds.discard(spec.kind)
        self._wake.set()

    def unregister(self, kind: str) -> None:
        """Unregister the handler of the kind. Its claimed jobs that haven't started yet are released."""
        if self._handlers.pop(kind, None) is None:
            return
        released = [job_id for job_id, (job, _) in self._pending.items() if job.kind == kind]
        for job_id in released:
            _, task = self._pending.pop(job_id)
            task.cancel()
        if released:
            self._background(self._release(released))

    def register_handlers(self, obj: object) -> list[str]:
        """Register every method of the object marked with `@handler`, e.g. all of a cog's.

        Returns
        -------
        list[str]
            The kinds that were registered.
        """
        kinds: list[str] = []
        for name, options in self._marked_methods(obj):
            self.register(HandlerSpec(func=getattr(obj, name), **options))
            kinds.append(options["kind"])
        return kinds

    def unregister_handlers(self, obj: object) -> None:
        """Unregister every handler that `register_handlers` registered for the object."""
        for _, options in self._marked_methods(obj):
            spec = self._handlers.get(options["kind"])
            if spec is not None and getattr(spec.func, "__self__", None) is obj:
                self.unregister(options["kind"])

    @staticmethod
    def _marked_methods(obj: object) -> list[tuple[str, dict[str, Any]]]:
        # Looking into the class dictionaries (instead of `inspect.getmembers`) doesn't evaluate properties.
        found: dict[str, dict[str, Any]] = {}
        for cls in reversed(type(obj).__mro__):
            for name, value in vars(cls).items():
                options = getattr(value, HANDLER_ATTRIBUTE, None)
                if options is not None:
                    found[name] = options
        return list(found.items())

    # --- SCHEDULING ---------------------------------------------------------------------------------------------------

    def now(self) -> dt.datetime:
        """Get the current moment by the scheduler's clock."""
        return self.clock()

    async def schedule(
        self,
        kind: str,
        when: When,
        *,
        data: JobData | None = None,
        key: str | None = None,
        user_id: int | None = None,
        guild_id: int | None = None,
        rule: str | None = None,
        timezone: str = UTC,
        on_conflict: OnConflict = "error",
    ) -> Job[Any]:
        """Schedule a job.

        Parameters
        ----------
        kind
            The kind of the job: which handler runs it.
        when
            When the job fires. A `WallTime` fires when the clocks of its timezone show its time
            (use it for times people set in their local time). An aware datetime is an absolute moment.
        data
            JSON-serializable data for the handler.
        key
            Unique name of the job; see `on_conflict` for what happens if a job with this key exists.
        user_id
            The user the job belongs to.
        guild_id
            The guild the job belongs to.
        rule
            RFC 5545 RRULE to repeat the job by, evaluated on the clocks of the job's timezone.
        timezone
            IANA timezone to read an aware `when` in, so the job (and its repeats) follow those clocks.
            The default, UTC, keeps it absolute.
        on_conflict
            If a job with the same `key` exists: "error" raises `JobExistsError`, "replace" replaces it
            (keeping its ID), "keep" leaves it as it is and returns it.

        Returns
        -------
        Job
            The scheduled job (or the kept one).

        Raises
        ------
        JobExistsError
            The key is taken and `on_conflict` is "error".
        ValueError
            The timezone or the rule is invalid.
        """
        wall = to_wall_time(when, timezone)
        if rule is not None:
            recurrence.validate_rule(rule, wall.local)

        conflict = {
            "error": "",
            "keep": "ON CONFLICT (key) DO NOTHING",
            "replace": """
                ON CONFLICT (key) DO UPDATE SET
                    kind = EXCLUDED.kind, user_id = EXCLUDED.user_id, guild_id = EXCLUDED.guild_id,
                    local_due = EXCLUDED.local_due, timezone = EXCLUDED.timezone, rule = EXCLUDED.rule,
                    data = EXCLUDED.data, created_at = EXCLUDED.created_at,
                    claimed_at = NULL, retry_at = NULL, attempts = 0, last_error = NULL
            """,
        }[on_conflict]
        query = f"""
            INSERT INTO scheduled_jobs (kind, key, user_id, guild_id, local_due, timezone, rule, data, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::JSONB, $9)
            {conflict}
            RETURNING {COLUMNS};
        """  # ruff: ignore[hardcoded-sql-expression]: only the constant pieces above are formatted in
        args = (kind, key, user_id, guild_id, wall.local, wall.timezone, rule, _json(data), self.clock())
        try:
            row = await self.pool.fetchrow(query, *args)
        except asyncpg.UniqueViolationError:
            raise JobExistsError(key or "") from None
        except asyncpg.InvalidParameterValueError as exc:
            msg = f"The database can't use the timezone {wall.timezone!r}: {exc}"
            raise ValueError(msg) from None

        if row is None:  # "keep" and the key is taken
            assert key is not None
            existing = await self.get_by_key(key)
            if existing is None:  # deleted in between, unlikely but possible
                return await self.schedule(kind, when, data=data, key=key, user_id=user_id, guild_id=guild_id,
                                           rule=rule, timezone=timezone, on_conflict="keep")  # fmt: skip
            return existing

        job = Job.from_row(row)
        self._forget(job.id)
        self._wake_if_soon(job.fire_at)
        return job

    async def update(
        self,
        job_id: int,
        *,
        kind: str | None = None,
        user_id: int | None = None,
        when: When | _Unset = UNSET,
        data: JobData | _Unset = UNSET,
        rule: str | _Unset | None = UNSET,
    ) -> Job[Any] | None:
        """Change a job. A pending retry and the failure count are reset.

        A job whose handler is running right now can't be changed: the handler's outcome decides what happens to it.

        Parameters
        ----------
        job_id
            ID of the job.
        kind
            If given, only a job of this kind is changed.
        user_id
            If given, only a job of this user is changed, e.g. to let users edit only their own reminders.
        when
            New time. Aware datetimes are read on the clocks of the job's timezone.
        data
            New data (replaces the old one).
        rule
            New repeat rule, `None` to stop repeating.

        Returns
        -------
        Job | None
            The changed job, or `None` if there is no such job or it's running right now.
        """
        if job_id in self._running:
            return None
        async with self.pool.acquire() as connection, connection.transaction():
            row = await connection.fetchrow(
                f"""
                    SELECT {COLUMNS} FROM scheduled_jobs
                    WHERE id = $1 AND ($2::TEXT IS NULL OR kind = $2) AND ($3::BIGINT IS NULL OR user_id = $3)
                    FOR UPDATE;
                """,  # ruff: ignore[hardcoded-sql-expression]: a constant
                job_id,
                kind,
                user_id,
            )
            if row is None:
                return None
            job = Job.from_row(row)

            wall = job.when if when is UNSET else to_wall_time(when, job.when.timezone)
            new_rule = job.rule if rule is UNSET else rule
            if new_rule is not None:
                recurrence.validate_rule(new_rule, wall.local)
            row = await connection.fetchrow(
                f"""
                    UPDATE scheduled_jobs SET
                        local_due = $2, timezone = $3, rule = $4, data = $5::JSONB,
                        claimed_at = NULL, retry_at = NULL, attempts = 0, last_error = NULL
                    WHERE id = $1
                    RETURNING {COLUMNS};
                """,  # ruff: ignore[hardcoded-sql-expression]: a constant
                job_id,
                wall.local,
                wall.timezone,
                new_rule,
                _json(job.data if data is UNSET else data),
            )
            assert row is not None, "the row is locked by this transaction"

        job = Job.from_row(row)
        self._forget(job.id)
        self._wake_if_soon(job.fire_at)
        return job

    async def run_now(self, job_id: int, *, kind: str | None = None, user_id: int | None = None) -> Job[Any] | None:
        """Fire a job right away, without waiting for its time.

        A repeating job fired before its time keeps that occurrence: it's not consumed by running early.

        Returns
        -------
        Job | None
            The job, or `None` if there is no such job or it's running right now.
        """
        if job_id in self._running:
            return None
        row = await self.pool.fetchrow(
            f"""
                UPDATE scheduled_jobs SET retry_at = $4, claimed_at = NULL
                WHERE id = $1 AND ($2::TEXT IS NULL OR kind = $2) AND ($3::BIGINT IS NULL OR user_id = $3)
                RETURNING {COLUMNS};
            """,  # ruff: ignore[hardcoded-sql-expression]: a constant
            job_id,
            kind,
            user_id,
            self.clock(),
        )
        if row is None:
            return None
        self._forget(job_id)
        self._wake.set()
        return Job.from_row(row)

    async def pause(self, job_id: int, *, kind: str | None = None, user_id: int | None = None) -> Job[Any] | None:
        """Pause a job: it doesn't fire until `resume`.

        Returns
        -------
        Job | None
            The paused job, or `None` if there is no such job or it's running right now.
        """
        if job_id in self._running:
            return None
        row = await self.pool.fetchrow(
            f"""
                UPDATE scheduled_jobs SET paused_at = $4, claimed_at = NULL, retry_at = NULL
                WHERE id = $1 AND ($2::TEXT IS NULL OR kind = $2) AND ($3::BIGINT IS NULL OR user_id = $3)
                RETURNING {COLUMNS};
            """,  # ruff: ignore[hardcoded-sql-expression]: a constant
            job_id,
            kind,
            user_id,
            self.clock(),
        )
        if row is None:
            return None
        self._forget(job_id)
        return Job.from_row(row)

    async def resume(self, job_id: int, *, kind: str | None = None, user_id: int | None = None) -> Job[Any] | None:
        """Resume a paused job.

        A repeating job whose occurrence passed while it was paused moves on to its next one after now
        (the missed ones are skipped, like after downtime). A one-off job whose time passed fires right away.

        Returns
        -------
        Job | None
            The resumed job, or `None` if there is no such job.
        """
        async with self.pool.acquire() as connection, connection.transaction():
            row = await connection.fetchrow(
                f"""
                    SELECT {COLUMNS} FROM scheduled_jobs
                    WHERE id = $1 AND ($2::TEXT IS NULL OR kind = $2) AND ($3::BIGINT IS NULL OR user_id = $3)
                    FOR UPDATE;
                """,  # ruff: ignore[hardcoded-sql-expression]: a constant
                job_id,
                kind,
                user_id,
            )
            if row is None:
                return None
            job = Job.from_row(row)
            when = job.when
            now = self.clock()
            if job.rule is not None and job.due_at <= now:
                local_now = WallTime.from_aware(now, when.timezone).local
                local = recurrence.next_occurrence(job.rule, current=when.local, after=local_now)
                if local is not None:
                    when = WallTime(local, when.timezone)
            row = await connection.fetchrow(
                f"""
                    UPDATE scheduled_jobs SET paused_at = NULL, local_due = $2, timezone = $3
                    WHERE id = $1
                    RETURNING {COLUMNS};
                """,  # ruff: ignore[hardcoded-sql-expression]: a constant
                job_id,
                when.local,
                when.timezone,
            )
            assert row is not None, "the row is locked by this transaction"
        job = Job.from_row(row)
        self._wake_if_soon(job.fire_at)
        return job

    async def history(
        self,
        kind: str | None = None,
        *,
        user_id: int | None = None,
        since: dt.datetime | None = None,
        outcomes: Sequence[str] | None = None,
        limit: int = 100,
    ) -> list[JobRun]:
        """Fetch past runs of jobs, the newest first (kept for `HISTORY_DAYS` days).

        Parameters
        ----------
        kind
            Only runs of jobs of this kind.
        user_id
            Only runs of this user's jobs.
        since
            Only runs that finished after this moment.
        outcomes
            Only runs with these outcomes, e.g. ``["failed", "gave_up"]``.
        limit
            At most this many runs.
        """
        rows = await self.pool.fetch(
            """
                SELECT * FROM scheduled_job_runs
                WHERE ($1::TEXT IS NULL OR kind = $1)
                    AND ($2::BIGINT IS NULL OR user_id = $2)
                    AND ($3::TIMESTAMPTZ IS NULL OR finished_at > $3)
                    AND ($4::TEXT[] IS NULL OR outcome = ANY($4::TEXT[]))
                ORDER BY finished_at DESC, id DESC
                LIMIT $5;
            """,
            kind,
            user_id,
            since,
            list(outcomes) if outcomes is not None else None,
            limit,
        )
        return [JobRun.from_row(row) for row in rows]

    # --- QUERYING -----------------------------------------------------------------------------------------------------

    async def get(self, job_id: int, *, kind: str | None = None, user_id: int | None = None) -> Job[Any] | None:
        """Get a job by its ID, optionally only if it has the given kind and/or user."""
        row = await self.pool.fetchrow(
            f"""
                SELECT {COLUMNS} FROM scheduled_jobs
                WHERE id = $1 AND ($2::TEXT IS NULL OR kind = $2) AND ($3::BIGINT IS NULL OR user_id = $3);
            """,  # ruff: ignore[hardcoded-sql-expression]: a constant
            job_id,
            kind,
            user_id,
        )
        return None if row is None else Job.from_row(row)

    async def get_by_key(self, key: str) -> Job[Any] | None:
        """Get a job by its key."""
        row = await self.pool.fetchrow(f"SELECT {COLUMNS} FROM scheduled_jobs WHERE key = $1;", key)  # ruff: ignore[hardcoded-sql-expression]
        return None if row is None else Job.from_row(row)

    async def fetch(
        self,
        kind: str | None = None,
        *,
        user_id: int | None = None,
        guild_id: int | None = None,
        limit: int | None = None,
    ) -> list[Job[Any]]:
        """Fetch jobs, the ones that fire first first.

        Parameters
        ----------
        kind
            Only jobs of this kind.
        user_id
            Only jobs of this user.
        guild_id
            Only jobs of this guild.
        limit
            At most this many jobs.
        """
        rows = await self.pool.fetch(
            f"""
                SELECT {COLUMNS} FROM scheduled_jobs
                WHERE ($1::TEXT IS NULL OR kind = $1)
                    AND ($2::BIGINT IS NULL OR user_id = $2)
                    AND ($3::BIGINT IS NULL OR guild_id = $3)
                ORDER BY {FIRE_AT}, id
                LIMIT $4;
            """,  # ruff: ignore[hardcoded-sql-expression]: constants
            kind,
            user_id,
            guild_id,
            limit,
        )
        return [Job.from_row(row) for row in rows]

    async def count(self, kind: str | None = None, *, user_id: int | None = None) -> int:
        """Count jobs, optionally only of the kind and/or the user (e.g. to limit reminders per user)."""
        query = """
            SELECT COUNT(*) FROM scheduled_jobs
            WHERE ($1::TEXT IS NULL OR kind = $1) AND ($2::BIGINT IS NULL OR user_id = $2);
        """
        return await self.pool.fetchval(query, kind, user_id)

    # --- DELETING -----------------------------------------------------------------------------------------------------

    async def delete(self, job_id: int, *, kind: str | None = None, user_id: int | None = None) -> Job[Any] | None:
        """Delete a job, optionally only if it has the given kind and/or user.

        Returns
        -------
        Job | None
            The deleted job, or `None` if there was no such job.
        """
        row = await self.pool.fetchrow(
            f"""
                DELETE FROM scheduled_jobs
                WHERE id = $1 AND ($2::TEXT IS NULL OR kind = $2) AND ($3::BIGINT IS NULL OR user_id = $3)
                RETURNING {COLUMNS};
            """,  # ruff: ignore[hardcoded-sql-expression]: a constant
            job_id,
            kind,
            user_id,
        )
        if row is None:
            return None
        self._forget(job_id)
        return Job.from_row(row)

    async def delete_by_key(self, key: str) -> Job[Any] | None:
        """Delete a job by its key; returns it, or `None` if there was no such job."""
        row = await self.pool.fetchrow(f"DELETE FROM scheduled_jobs WHERE key = $1 RETURNING {COLUMNS};", key)  # ruff: ignore[hardcoded-sql-expression]
        if row is None:
            return None
        self._forget(row["id"])
        return Job.from_row(row)

    async def delete_where(
        self, kind: str, *, user_id: int | None = None, guild_id: int | None = None
    ) -> list[Job[Any]]:
        """Delete all jobs of the kind, optionally only the user's and/or the guild's; returns them."""
        rows = await self.pool.fetch(
            f"""
                DELETE FROM scheduled_jobs
                WHERE kind = $1 AND ($2::BIGINT IS NULL OR user_id = $2) AND ($3::BIGINT IS NULL OR guild_id = $3)
                RETURNING {COLUMNS};
            """,  # ruff: ignore[hardcoded-sql-expression]: a constant
            kind,
            user_id,
            guild_id,
        )
        for row in rows:
            self._forget(row["id"])
        return [Job.from_row(row) for row in rows]

    # --- LOOP ---------------------------------------------------------------------------------------------------------

    async def _run(self, wait_until: Callable[[], Awaitable[object]] | None) -> None:
        if wait_until is not None:
            await wait_until()

        delay = MIN_LOOP_RETRY
        while not self._closing:
            self._wake.clear()
            try:
                await self._poll()
                # after the poll: the listener only speeds things up, so (re)connecting it mustn't delay jobs
                await self._ensure_listener()
            except (OSError, TimeoutError, asyncpg.PostgresConnectionError, asyncpg.InterfaceError) as exc:
                logger.warning("Scheduler: the database is unavailable ({!r}), retrying in {:.0f}s.", exc, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_LOOP_RETRY)
                continue
            except Exception as exc:  # ruff: ignore[blind-except]: the loop must survive anything
                await self._report(exc, None)
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_LOOP_RETRY)
                continue

            delay = MIN_LOOP_RETRY
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(self.poll_interval.total_seconds()):
                    await self._wake.wait()

    async def _poll(self) -> None:
        now = self.clock()
        if self._handlers:
            rows = await self.pool.fetch(
                f"""
                    WITH due AS (
                        SELECT id FROM scheduled_jobs
                        WHERE claimed_at IS NULL AND paused_at IS NULL AND kind = ANY($3::TEXT[]) AND {FIRE_AT} <= $2
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE scheduled_jobs AS jobs SET claimed_at = $1
                    FROM due WHERE jobs.id = due.id
                    RETURNING jobs.*, (jobs.local_due AT TIME ZONE jobs.timezone) AS due_at;
                """,  # ruff: ignore[hardcoded-sql-expression]: a constant
                now,
                now + self.lookahead,
                list(self._handlers),
            )
            for row in rows:
                self._spawn(Job.from_row(row))
        await self._warn_about_unknown_kinds(now)

    async def _warn_about_unknown_kinds(self, now: dt.datetime) -> None:
        checked_at = self._unknown_kinds_checked_at
        if checked_at is not None and now - checked_at < UNKNOWN_KINDS_CHECK_INTERVAL:
            return
        self._unknown_kinds_checked_at = now
        await self.pool.execute(
            "DELETE FROM scheduled_job_runs WHERE finished_at < $1", now - dt.timedelta(days=HISTORY_DAYS)
        )
        rows = await self.pool.fetch(
            f"""
                SELECT kind, COUNT(*) AS total FROM scheduled_jobs
                WHERE claimed_at IS NULL AND paused_at IS NULL AND NOT (kind = ANY($1::TEXT[])) AND {FIRE_AT} < $2
                GROUP BY kind;
            """,  # ruff: ignore[hardcoded-sql-expression]: a constant
            list(self._handlers),
            now - UNKNOWN_KINDS_GRACE,
        )
        for row in rows:
            if row["kind"] not in self._warned_kinds:
                self._warned_kinds.add(row["kind"])
                logger.warning(
                    "Scheduler: {} overdue jobs of the kind {!r} have no handler.", row["total"], row["kind"]
                )

    # --- FIRING -------------------------------------------------------------------------------------------------------

    def _spawn(self, job: Job) -> None:
        task = asyncio.create_task(self._fire(job), name=f"scheduler-job-{job.id}")
        self._pending[job.id] = (job, task)

    async def _fire(self, job: Job) -> None:
        await self._sleep_until(job.fire_at)

        # From here on the job counts as running: nothing but `close` cancels it.
        # There is no `await` between leaving `_pending` and entering `_running`.
        task = asyncio.current_task()
        assert task is not None
        self._pending.pop(job.id, None)
        self._running[job.id] = task
        try:
            await self._execute(job)
        except Exception as exc:  # ruff: ignore[blind-except]: e.g. the database is down while finishing the job
            # the job stays claimed: it's released and runs again after the next start
            await self._report(exc, job)
        finally:
            self._running.pop(job.id, None)

    async def _sleep_until(self, moment: dt.datetime) -> None:
        # Sleep in steps and re-check the clock: `asyncio.sleep` counts monotonic time, which drifts from the wall
        # clock (NTP adjustments, a suspended machine).
        while (seconds := (moment - self.clock()).total_seconds()) > 0:  # ruff: ignore[async-busy-wait]
            await asyncio.sleep(min(seconds, self.poll_interval.total_seconds()))

    async def _execute(self, job: Job) -> None:
        spec = self._handlers.get(job.kind)
        if spec is None:  # unregistered while the job waited
            await self._release([job.id])
            return

        # at most `max_concurrency` handlers at once: after downtime, the rest wait here for a free slot
        async with self._slots:
            now = self.clock()
            job = dataclasses.replace(job, fired_at=now)
            if spec.max_lateness is not None and job.lateness > spec.max_lateness:
                logger.info("Scheduler: skipping {} job {}, it's {} late.", job.kind, job.id, job.lateness)
                await self._finish(job, spec, None, now, record="skipped")
                return

            logger.debug("Scheduler: firing {} job {} (due {}).", job.kind, job.id, job.due_at)
            try:
                outcome = await spec.func(job)
            except Exception as exc:  # ruff: ignore[blind-except]: handler errors are retried
                await self._fail(job, spec, exc, now)
                return
            await self._finish(job, spec, outcome, now)

    async def _finish(
        self,
        job: Job,
        spec: HandlerSpec,
        outcome: Outcome,
        now: dt.datetime,
        *,
        last_error: str | None = None,
        record: str | None = None,
    ) -> None:
        if outcome is STOP:
            next_when = None
        elif isinstance(outcome, Reschedule):
            next_when = to_wall_time(outcome.when, job.when.timezone)
        elif job.due_at > now:
            # fired early with `run_now`: the occurrence itself is still ahead
            next_when = job.when
        else:
            next_when = self._next_occurrence(job, spec, now)

        default = "stopped" if outcome is STOP else "rescheduled" if isinstance(outcome, Reschedule) else "done"
        await self._record(job, record or default, error=last_error)

        if next_when is None:
            await self.pool.execute(
                "DELETE FROM scheduled_jobs WHERE id = $1 AND claimed_at = $2;", job.id, job.claimed_at
            )
            return

        row = await self.pool.fetchrow(
            f"""
                UPDATE scheduled_jobs SET
                    local_due = $3, timezone = $4, claimed_at = NULL, retry_at = NULL, attempts = 0, last_error = $5
                WHERE id = $1 AND claimed_at = $2
                RETURNING {FIRE_AT} AS fire_at;
            """,  # ruff: ignore[hardcoded-sql-expression]: a constant
            job.id,
            job.claimed_at,
            next_when.local,
            next_when.timezone,
            last_error,
        )
        if row is not None:
            self._wake_if_soon(row["fire_at"])

    def _next_occurrence(self, job: Job, spec: HandlerSpec, now: dt.datetime) -> WallTime | None:
        if spec.recur is not None:
            when = spec.recur(job, now)
            return None if when is None else to_wall_time(when, job.when.timezone)
        if job.rule is None:
            return None
        local_now = WallTime.from_aware(now, job.when.timezone).local
        local = recurrence.next_occurrence(job.rule, current=job.when.local, after=local_now)
        return None if local is None else WallTime(local, job.when.timezone)

    async def _fail(self, job: Job, spec: HandlerSpec, exc: Exception, now: dt.datetime) -> None:
        attempts = job.attempts + 1
        error = "".join(traceback.format_exception(exc))
        await self._report(exc, job)

        if attempts >= spec.max_attempts:
            logger.warning("Scheduler: giving up on {} job {} after {} attempts.", job.kind, job.id, attempts)
            # the occurrence is over: one-off jobs are deleted, repeating ones move on (keeping the error to look at)
            await self._finish(job, spec, None, now, last_error=error, record="gave_up")
            return

        await self._record(job, "failed", error=error)
        retry_at = now + spec.retry_delay * 2 ** (attempts - 1)
        await self.pool.execute(
            """
                UPDATE scheduled_jobs SET claimed_at = NULL, retry_at = $3, attempts = $4, last_error = $5
                WHERE id = $1 AND claimed_at = $2;
            """,
            job.id,
            job.claimed_at,
            retry_at,
            attempts,
            error,
        )
        self._wake_if_soon(retry_at)

    # --- HELPERS ------------------------------------------------------------------------------------------------------

    async def _record(self, job: Job, outcome: str, *, error: str | None = None) -> None:
        """Add a row to the run history. A failure to write it is reported, not raised: history is a nicety."""
        try:
            await self.pool.execute(
                """
                    INSERT INTO scheduled_job_runs
                        (job_id, kind, key, user_id, guild_id, due_at, fired_at, finished_at, attempt, outcome, error)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11);
                """,
                job.id,
                job.kind,
                job.key,
                job.user_id,
                job.guild_id,
                job.due_at,
                job.fired_at or self.clock(),
                self.clock(),
                job.attempts + 1,
                outcome,
                error,
            )
        except Exception as exc:  # ruff: ignore[blind-except]
            await self._report(exc, job)

    async def _ensure_listener(self) -> None:
        """Hold a connection that `LISTEN`s for changes of the table made elsewhere (e.g. "run now" from LalaBot).

        Without it everything still works, just on the next poll instead of right away, so failures are only logged.
        """
        if self._listener is not None and not self._listener.is_closed():
            return
        await self._drop_listener()
        try:
            connection = await self.pool.acquire()
        except Exception:  # ruff: ignore[blind-except]
            logger.opt(exception=True).warning("Scheduler: no connection to LISTEN on, polling only.")
            return
        try:
            await connection.add_listener(NOTIFY_CHANNEL, self._on_notify)
        except Exception:  # ruff: ignore[blind-except]
            logger.opt(exception=True).warning("Scheduler: could not LISTEN, polling only.")
            await self.pool.release(connection)
            return
        self._listener = connection

    async def _drop_listener(self) -> None:
        if (connection := self._listener) is None:
            return
        self._listener = None
        with contextlib.suppress(Exception):
            await connection.remove_listener(NOTIFY_CHANNEL, self._on_notify)
        with contextlib.suppress(Exception):
            await self.pool.release(connection)

    def _on_notify(self, _connection: Any, _pid: int, _channel: str, payload: object) -> None:
        # every bot's table notifies the same channel: only wake up for this one's
        if payload == self._schema:
            self._wake.set()

    def _forget(self, job_id: int) -> None:
        """Drop a job's waiting task after its row was changed or deleted (and its claim with it)."""
        if (entry := self._pending.pop(job_id, None)) is not None:
            entry[1].cancel()

    def _wake_if_soon(self, moment: dt.datetime) -> None:
        if moment - self.clock() <= self.lookahead:
            self._wake.set()

    async def _release(self, job_ids: Sequence[int]) -> None:
        await self.pool.execute("UPDATE scheduled_jobs SET claimed_at = NULL WHERE id = ANY($1::BIGINT[]);", job_ids)

    def _background(self, coro: Awaitable[object]) -> None:
        async def runner() -> None:
            try:
                await coro
            except Exception as exc:  # ruff: ignore[blind-except]
                await self._report(exc, None)

        task = asyncio.create_task(runner())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _report(self, exc: BaseException, job: Job | None) -> None:
        if job is None:
            logger.opt(exception=exc).error("Scheduler error.")
        else:
            logger.opt(exception=exc).error(
                "Scheduler: {} job {} failed (attempt {}).", job.kind, job.id, job.attempts + 1
            )
        if self._on_error is not None:
            try:
                await self._on_error(exc, job)
            except Exception:  # ruff: ignore[blind-except]
                logger.opt(exception=True).error("Scheduler: the error callback failed.")

    @property
    def kinds(self) -> list[str]:
        """The kinds that have a handler."""
        return list(self._handlers)

    @override
    def __repr__(self) -> str:
        return (
            f"<Scheduler kinds={self.kinds} pending={len(self._pending)} running={len(self._running)}"
            f" closing={self._closing}>"
        )
