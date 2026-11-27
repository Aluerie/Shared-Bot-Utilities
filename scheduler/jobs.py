# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Jobs, what their handlers return and the decorator that turns methods into handlers."""

import datetime as dt
import enum
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Self

from .walltime import WallTime, When

__all__ = (
    "STOP",
    "Handler",
    "HandlerSpec",
    "Job",
    "JobData",
    "JobRun",
    "Outcome",
    "Recur",
    "Reschedule",
    "Stop",
    "handler",
)


type JobData = Mapping[str, Any]
"""JSON-serializable data of a job. Handlers usually narrow it with a ``TypedDict``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Job[DataT: JobData = JobData]:
    """A scheduled job, as stored in the ``scheduled_jobs`` table.

    Attributes
    ----------
    id
        Unique ID of the job, also shown to users (e.g. reminder IDs).
    kind
        What the job is, e.g. "reminder". Decides which handler runs it.
    key
        Optional unique name of the job, e.g. "birthday:123". Scheduling another job with the same key
        replaces it (or keeps the old one), so there is never more than one.
    user_id
        The user the job belongs to, if any. Used to list and delete a user's jobs.
    guild_id
        The guild the job belongs to, if any.
    when
        The scheduled occurrence: a wall time in the job's timezone (UTC for absolute jobs).
    due_at
        The moment `when` stands for (aware, UTC), as resolved by the database.
    rule
        RFC 5545 RRULE the job repeats by, if any.
    data
        The job's data, read-only.
    created_at
        When the job was created (aware, UTC).
    attempts
        How many times the current occurrence failed so far.
    last_error
        Traceback of the last failure, if any.
    retry_at
        If set, the job fires at this moment instead of `due_at`: a retry after a failure or `Scheduler.run_now`.
    claimed_at
        When the scheduler claimed the job to run it; `None` while it's waiting.
    paused_at
        When the job was paused (`Scheduler.pause`); `None` unless it's paused. Paused jobs don't fire.
    fired_at
        When the job's handler was called, for jobs passed to handlers; `None` otherwise.
    """

    id: int
    kind: str
    key: str | None
    user_id: int | None
    guild_id: int | None
    when: WallTime
    due_at: dt.datetime
    rule: str | None
    data: DataT
    created_at: dt.datetime
    attempts: int = 0
    last_error: str | None = None
    retry_at: dt.datetime | None = None
    claimed_at: dt.datetime | None = None
    paused_at: dt.datetime | None = None
    fired_at: dt.datetime | None = field(default=None, compare=False)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        """Make a job from a database row (with the computed ``due_at`` column)."""
        return cls(
            id=row["id"],
            kind=row["kind"],
            key=row["key"],
            user_id=row["user_id"],
            guild_id=row["guild_id"],
            when=WallTime(row["local_due"], row["timezone"]),
            due_at=row["due_at"].astimezone(dt.UTC),
            rule=row["rule"],
            data=frozendict(row["data"]),
            created_at=row["created_at"].astimezone(dt.UTC),
            attempts=row["attempts"],
            last_error=row["last_error"],
            retry_at=row["retry_at"] and row["retry_at"].astimezone(dt.UTC),
            claimed_at=row["claimed_at"],
            paused_at=row["paused_at"] and row["paused_at"].astimezone(dt.UTC),
        )

    @property
    def is_paused(self) -> bool:
        """Whether the job is paused."""
        return self.paused_at is not None

    @property
    def fire_at(self) -> dt.datetime:
        """The moment the job fires: `retry_at` if it's set, otherwise `due_at`."""
        return self.retry_at or self.due_at

    @property
    def lateness(self) -> dt.timedelta:
        """How late the handler was called compared to `due_at`. Zero for jobs that aren't firing."""
        if self.fired_at is None:
            return dt.timedelta()
        return max(self.fired_at - self.due_at, dt.timedelta())


@dataclass(frozen=True, slots=True, kw_only=True)
class JobRun:
    """A past run of a job (or a skipped occurrence), from the ``scheduled_job_runs`` history.

    Attributes
    ----------
    job_id
        ID of the job; the job itself may be gone.
    kind
        The job's kind.
    key
        The job's key, if any.
    user_id
        The job's user, if any.
    guild_id
        The job's guild, if any.
    due_at
        When the occurrence was due.
    fired_at
        When the handler was called (or the occurrence was skipped).
    finished_at
        When the run was over.
    attempt
        Which try of the occurrence this was, 1 for the first.
    outcome
        "done", "rescheduled", "stopped", "skipped" (too late), "failed" (retried later) or "gave_up".
    error
        Traceback, for "failed" and "gave_up".
    """

    job_id: int
    kind: str
    key: str | None
    user_id: int | None
    guild_id: int | None
    due_at: dt.datetime
    fired_at: dt.datetime
    finished_at: dt.datetime
    attempt: int
    outcome: str
    error: str | None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Self:
        """Make a run from a ``scheduled_job_runs`` row."""
        return cls(
            job_id=row["job_id"],
            kind=row["kind"],
            key=row["key"],
            user_id=row["user_id"],
            guild_id=row["guild_id"],
            due_at=row["due_at"].astimezone(dt.UTC),
            fired_at=row["fired_at"].astimezone(dt.UTC),
            finished_at=row["finished_at"].astimezone(dt.UTC),
            attempt=row["attempt"],
            outcome=row["outcome"],
            error=row["error"],
        )

    @property
    def lateness(self) -> dt.timedelta:
        """How late the run started compared to when the occurrence was due."""
        return max(self.fired_at - self.due_at, dt.timedelta())


# --- OUTCOMES ---------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Reschedule:
    """Handler outcome: keep the job and fire it again at `when`, instead of deleting or repeating it as usual.

    Aware datetimes are read on the clocks of the job's timezone.
    """

    when: When


class Stop(enum.Enum):
    """Handler outcome: delete the job, even if it repeats."""

    STOP = enum.auto()


STOP = Stop.STOP
"""Handler outcome: delete the job, even if it repeats."""

type Outcome = Reschedule | Stop | None
"""What a handler returns. `None` is the usual: one-off jobs are deleted, repeating jobs move to the next occurrence."""

type Handler[DataT: JobData = Any] = Callable[[Job[DataT]], Awaitable[Outcome]]
"""Coroutine function that runs a job."""

type Recur = Callable[[Job[Any], dt.datetime], When | None]
"""Function that gets the next occurrence of a repeating kind: ``(job, now) -> when``, `None` to stop.

``now`` is an aware UTC datetime. Used for repeats that an RRULE can't express (birthdays on the 29th of February,
random intervals).
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class HandlerSpec:
    """A handler for one kind of jobs and how the scheduler treats those jobs.

    Attributes
    ----------
    kind
        The kind of jobs the handler runs.
    func
        The handler.
    recur
        Custom repeat for every job of this kind. Takes precedence over the jobs' RRULEs.
    max_lateness
        Occurrences that would run later than this after they were due are skipped (not run, but still repeated).
        `None` runs them however late it is.
    max_attempts
        How many times an occurrence is tried before it's given up on.
    retry_delay
        Delay before the first retry; it doubles with each following one.
    """

    kind: str
    func: Handler
    recur: Recur | None = None
    max_lateness: dt.timedelta | None = None
    max_attempts: int = 3
    retry_delay: dt.timedelta = dt.timedelta(minutes=1)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            msg = f"max_attempts must be at least 1, got {self.max_attempts}."
            raise ValueError(msg)


HANDLER_ATTRIBUTE = "__scheduler_handler__"
"""Attribute that `handler` puts on decorated functions."""


def handler[F: Callable[..., Awaitable[Outcome]]](
    kind: str,
    *,
    recur: Recur | None = None,
    max_lateness: dt.timedelta | None = None,
    max_attempts: int = 3,
    retry_delay: dt.timedelta = dt.timedelta(minutes=1),
) -> Callable[[F], F]:
    """Mark a method as the handler of a kind of jobs.

    `Scheduler.register_handlers` registers every marked method of an object (e.g. a cog).

    .. code-block:: python

        class Reminders(Cog):
            @scheduler.handler("reminder")
            async def send_reminder(self, job: Job[ReminderData]) -> None: ...

    Parameters
    ----------
    kind
        The kind of jobs the handler runs.
    recur
        Custom repeat for every job of this kind, see `HandlerSpec.recur`.
    max_lateness
        Skip occurrences that are later than this, see `HandlerSpec.max_lateness`.
    max_attempts
        How many times an occurrence is tried, see `HandlerSpec.max_attempts`.
    retry_delay
        Delay before the first retry, see `HandlerSpec.retry_delay`.
    """
    options = {
        "kind": kind,
        "recur": recur,
        "max_lateness": max_lateness,
        "max_attempts": max_attempts,
        "retry_delay": retry_delay,
    }

    def decorator(func: F) -> F:
        setattr(func, HANDLER_ATTRIBUTE, options)
        return func

    return decorator
