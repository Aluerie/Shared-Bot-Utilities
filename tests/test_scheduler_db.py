# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
# ruff: file-ignore[call-datetime-without-tzinfo]  # wall times are naive on purpose
"""Integration tests for the scheduler against a real PostgreSQL.

They run only when the ``SHARED_TEST_POSTGRES`` environment variable holds a connection string.
Each test works in its own throwaway schema, which is dropped afterwards.
"""

import asyncio
import datetime as dt
import os
import secrets
from typing import TYPE_CHECKING, Any

import asyncpg
import orjson
import pytest

from shared.scheduler import (
    STOP,
    HandlerSpec,
    Job,
    JobExistsError,
    Reschedule,
    Scheduler,
    WallTime,
    resolve,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

DSN = os.environ.get("SHARED_TEST_POSTGRES")
pytestmark = pytest.mark.skipif(DSN is None, reason="SHARED_TEST_POSTGRES is not set")

POLL = dt.timedelta(seconds=0.2)
BERLIN = "Europe/Berlin"


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


@pytest.fixture
async def pool() -> AsyncIterator[asyncpg.Pool[Any]]:
    assert DSN is not None
    schema = f"scheduler_test_{secrets.token_hex(4)}"
    admin = await asyncpg.connect(DSN)
    await admin.execute(f"CREATE SCHEMA {schema}")

    async def init(connection: asyncpg.Connection[Any]) -> None:
        await connection.set_type_codec(
            "jsonb",
            schema="pg_catalog",
            encoder=lambda value: orjson.dumps(value).decode(),
            decoder=orjson.loads,
            format="text",
        )

    test_pool = await asyncpg.create_pool(
        DSN, min_size=1, max_size=4, init=init, server_settings={"search_path": schema}
    )
    try:
        yield test_pool
    finally:
        await test_pool.close()
        await admin.execute(f"DROP SCHEMA {schema} CASCADE")
        await admin.close()


class Recorder:
    """Handler that records the jobs it gets and returns (or raises) what it's told."""

    def __init__(self, outcome: Any = None, *, fail_times: int = 0) -> None:
        self.jobs: list[Job] = []
        self.outcome: Any = outcome
        self.fail_times: int = fail_times
        self.called: asyncio.Event = asyncio.Event()

    async def __call__(self, job: Job) -> Any:
        self.jobs.append(job)
        self.called.set()
        if self.fail_times > 0:
            self.fail_times -= 1
            msg = "boom"
            raise RuntimeError(msg)
        return self.outcome() if callable(self.outcome) else self.outcome

    async def wait(self, count: int = 1, within: float = 5.0) -> None:
        async with asyncio.timeout(within):
            while len(self.jobs) < count:
                self.called.clear()
                await self.called.wait()


@pytest.fixture
async def make_scheduler(pool: asyncpg.Pool[Any]) -> AsyncIterator[Callable[..., Scheduler]]:
    schedulers: list[Scheduler] = []

    def factory(**kwargs: Any) -> Scheduler:
        kwargs.setdefault("poll_interval", POLL)
        scheduler = Scheduler(pool, **kwargs)
        schedulers.append(scheduler)
        return scheduler

    yield factory
    for scheduler in schedulers:
        await scheduler.close(grace_period=1)


async def started(factory: Callable[..., Scheduler], *specs: HandlerSpec, **kwargs: Any) -> Scheduler:
    scheduler = factory(**kwargs)
    for spec in specs:
        scheduler.register(spec)
    await scheduler.start()
    return scheduler


async def row_count(pool: asyncpg.Pool[Any]) -> int:
    return await pool.fetchval("SELECT COUNT(*) FROM scheduled_jobs")


# --- FIRING -----------------------------------------------------------------------------------------------------------


async def test_one_off_job_fires_once_and_is_deleted(make_scheduler: Any, pool: Any) -> None:
    recorder = Recorder()
    scheduler = await started(make_scheduler, HandlerSpec(kind="ping", func=recorder))

    due = utcnow() + dt.timedelta(seconds=0.5)
    job = await scheduler.schedule("ping", due, data={"text": "hi"}, user_id=1)
    await recorder.wait()

    fired = recorder.jobs[0]
    assert fired.id == job.id
    assert fired.data["text"] == "hi"
    assert fired.fired_at is not None
    assert fired.fired_at >= due
    await asyncio.sleep(0.2)
    assert await row_count(pool) == 0


async def test_short_job_does_not_wait_for_the_next_poll(make_scheduler: Any) -> None:
    recorder = Recorder()
    scheduler = await started(
        make_scheduler, HandlerSpec(kind="ping", func=recorder), poll_interval=dt.timedelta(seconds=30)
    )
    await asyncio.sleep(0.1)  # the loop is asleep now
    await scheduler.schedule("ping", utcnow() + dt.timedelta(seconds=0.3))
    await recorder.wait(within=2)


async def test_database_and_python_agree_on_dst_moments(make_scheduler: Any) -> None:
    scheduler = make_scheduler()
    await scheduler.install()
    for local in (dt.datetime(2026, 3, 29, 2, 30), dt.datetime(2026, 10, 25, 2, 30), dt.datetime(2026, 7, 1, 12)):
        job = await scheduler.schedule("x", WallTime(local, BERLIN))
        assert job.due_at == resolve(local, BERLIN) == job.when.to_utc()


async def test_repeating_job_moves_to_the_next_occurrence_on_its_clock(make_scheduler: Any, pool: Any) -> None:
    recorder = Recorder()
    scheduler = await started(make_scheduler, HandlerSpec(kind="daily", func=recorder))

    # due a few days ago: runs once, then moves to the first 09:00 Berlin time after now
    local = WallTime.from_aware(utcnow(), BERLIN).local.replace(hour=9, minute=0, second=0, microsecond=0)
    start = WallTime(local - dt.timedelta(days=3), BERLIN)
    job = await scheduler.schedule("daily", start, rule="FREQ=DAILY")
    await recorder.wait()
    await asyncio.sleep(0.3)

    moved = await scheduler.get(job.id)
    assert moved is not None
    assert len(recorder.jobs) == 1
    assert moved.when.local.time() == dt.time(9)
    assert moved.due_at > utcnow()
    assert moved.due_at - utcnow() <= dt.timedelta(days=1)
    assert await row_count(pool) == 1


async def test_custom_recur_takes_precedence(make_scheduler: Any) -> None:
    recorder = Recorder()
    later = utcnow() + dt.timedelta(days=30)
    spec = HandlerSpec(kind="custom", func=recorder, recur=lambda _job, _now: later)
    scheduler = await started(make_scheduler, spec)

    job = await scheduler.schedule("custom", utcnow())
    await recorder.wait()
    await asyncio.sleep(0.3)
    moved = await scheduler.get(job.id)
    assert moved is not None
    assert abs(moved.due_at - later) < dt.timedelta(milliseconds=1)


# --- OUTCOMES ---------------------------------------------------------------------------------------------------------


async def test_reschedule_outcome_keeps_the_job(make_scheduler: Any) -> None:
    target = utcnow() + dt.timedelta(hours=1)
    recorder = Recorder(Reschedule(target))
    scheduler = await started(make_scheduler, HandlerSpec(kind="later", func=recorder))

    job = await scheduler.schedule("later", utcnow())
    await recorder.wait()
    await asyncio.sleep(0.3)
    kept = await scheduler.get(job.id)
    assert kept is not None
    assert abs(kept.due_at - target) < dt.timedelta(milliseconds=1)


async def test_stop_outcome_ends_a_repeating_job(make_scheduler: Any, pool: Any) -> None:
    recorder = Recorder(STOP)
    scheduler = await started(make_scheduler, HandlerSpec(kind="daily", func=recorder))
    await scheduler.schedule("daily", utcnow(), rule="FREQ=DAILY")
    await recorder.wait()
    await asyncio.sleep(0.3)
    assert await row_count(pool) == 0


# --- FAILURES AND LATENESS --------------------------------------------------------------------------------------------


async def test_failed_job_is_retried_then_given_up(make_scheduler: Any, pool: Any) -> None:
    errors: list[tuple[BaseException, Job | None]] = []

    async def on_error(exc: BaseException, job: Job | None) -> None:
        errors.append((exc, job))

    recorder = Recorder(fail_times=10)
    spec = HandlerSpec(kind="flaky", func=recorder, max_attempts=3, retry_delay=dt.timedelta(seconds=0.1))
    scheduler = await started(make_scheduler, spec, on_error=on_error)

    await scheduler.schedule("flaky", utcnow())
    await recorder.wait(count=3)
    await asyncio.sleep(0.5)

    assert len(recorder.jobs) == 3
    assert [job.attempts for job in recorder.jobs] == [0, 1, 2]
    assert len(errors) == 3
    assert all(job is not None for _, job in errors)
    assert await row_count(pool) == 0  # a one-off job is deleted after the last attempt


async def test_failed_repeating_job_moves_on_and_keeps_the_error(make_scheduler: Any) -> None:
    recorder = Recorder(fail_times=10)
    spec = HandlerSpec(kind="flaky", func=recorder, max_attempts=1)
    scheduler = await started(make_scheduler, spec)

    job = await scheduler.schedule("flaky", utcnow(), rule="FREQ=DAILY")
    await recorder.wait()
    await asyncio.sleep(0.3)
    moved = await scheduler.get(job.id)
    assert moved is not None
    assert moved.due_at > utcnow()
    assert moved.attempts == 0
    assert moved.last_error is not None
    assert "boom" in moved.last_error


async def test_job_recovers_after_a_failure(make_scheduler: Any, pool: Any) -> None:
    recorder = Recorder(fail_times=1)
    spec = HandlerSpec(kind="flaky", func=recorder, retry_delay=dt.timedelta(seconds=0.1))
    scheduler = await started(make_scheduler, spec)
    await scheduler.schedule("flaky", utcnow())
    await recorder.wait(count=2)
    await asyncio.sleep(0.3)
    assert await row_count(pool) == 0


async def test_too_late_job_is_skipped(make_scheduler: Any, pool: Any) -> None:
    recorder = Recorder()
    spec = HandlerSpec(kind="birthday", func=recorder, max_lateness=dt.timedelta(days=1))
    scheduler = await started(make_scheduler, spec)
    await scheduler.schedule("birthday", utcnow() - dt.timedelta(days=2))
    await asyncio.sleep(0.6)
    assert recorder.jobs == []
    assert await row_count(pool) == 0


async def test_late_job_reports_its_lateness(make_scheduler: Any) -> None:
    recorder = Recorder()
    scheduler = await started(make_scheduler, HandlerSpec(kind="ping", func=recorder))
    await scheduler.schedule("ping", utcnow() - dt.timedelta(hours=3))
    await recorder.wait()
    assert recorder.jobs[0].lateness >= dt.timedelta(hours=3)


# --- KEYS, CHANGES, DELETION ------------------------------------------------------------------------------------------


async def test_key_conflicts(make_scheduler: Any) -> None:
    scheduler = make_scheduler()
    await scheduler.install()
    soon, later = utcnow() + dt.timedelta(days=1), utcnow() + dt.timedelta(days=2)

    first = await scheduler.schedule("birthday", soon, key="birthday:1", data={"v": 1})
    with pytest.raises(JobExistsError):
        await scheduler.schedule("birthday", later, key="birthday:1")

    kept = await scheduler.schedule("birthday", later, key="birthday:1", on_conflict="keep")
    assert kept.id == first.id
    assert kept.data["v"] == 1

    replaced = await scheduler.schedule("birthday", later, key="birthday:1", data={"v": 2}, on_conflict="replace")
    assert replaced.id == first.id
    assert replaced.data["v"] == 2
    assert abs(replaced.due_at - later) < dt.timedelta(milliseconds=1)


async def test_deleted_job_does_not_fire(make_scheduler: Any) -> None:
    recorder = Recorder()
    scheduler = await started(make_scheduler, HandlerSpec(kind="ping", func=recorder))
    job = await scheduler.schedule("ping", utcnow() + dt.timedelta(seconds=0.6))
    await asyncio.sleep(0.3)  # claimed by now: it's within the look-ahead window
    assert await scheduler.delete(job.id, user_id=None) is not None
    await asyncio.sleep(0.6)
    assert recorder.jobs == []


async def test_delete_respects_the_owner(make_scheduler: Any) -> None:
    scheduler = make_scheduler()
    await scheduler.install()
    job = await scheduler.schedule("reminder", utcnow() + dt.timedelta(days=1), user_id=1)
    assert await scheduler.delete(job.id, kind="reminder", user_id=2) is None
    assert await scheduler.delete(job.id, kind="other", user_id=1) is None
    assert await scheduler.delete(job.id, kind="reminder", user_id=1) is not None


async def test_updated_job_fires_at_its_new_time(make_scheduler: Any) -> None:
    recorder = Recorder()
    scheduler = await started(make_scheduler, HandlerSpec(kind="ping", func=recorder))
    job = await scheduler.schedule("ping", utcnow() + dt.timedelta(seconds=0.5), data={"text": "old"})
    await asyncio.sleep(0.25)
    await scheduler.update(job.id, when=utcnow() + dt.timedelta(seconds=1.2), data={"text": "new"})
    await asyncio.sleep(0.6)
    assert recorder.jobs == []
    await recorder.wait()
    assert recorder.jobs[0].data["text"] == "new"


async def test_fetch_and_count(make_scheduler: Any) -> None:
    scheduler = make_scheduler()
    await scheduler.install()
    now = utcnow()
    await scheduler.schedule("reminder", now + dt.timedelta(days=2), user_id=1)
    await scheduler.schedule("reminder", now + dt.timedelta(days=1), user_id=1)
    await scheduler.schedule("reminder", now + dt.timedelta(days=1), user_id=2)
    await scheduler.schedule("birthday", now + dt.timedelta(days=1), user_id=1)

    mine = await scheduler.fetch("reminder", user_id=1)
    assert [job.due_at for job in mine] == sorted(job.due_at for job in mine)
    assert len(mine) == 2
    assert await scheduler.count("reminder", user_id=1) == 2
    assert await scheduler.count("reminder") == 3
    assert len(await scheduler.delete_where("reminder", user_id=1)) == 2
    assert await scheduler.count() == 2


# --- RUN NOW ----------------------------------------------------------------------------------------------------------


async def test_run_now_keeps_the_upcoming_occurrence_of_a_repeating_job(make_scheduler: Any) -> None:
    recorder = Recorder()
    scheduler = await started(make_scheduler, HandlerSpec(kind="daily", func=recorder))
    tomorrow = WallTime.from_aware(utcnow() + dt.timedelta(days=1), BERLIN)
    job = await scheduler.schedule("daily", tomorrow, rule="FREQ=DAILY")

    await scheduler.run_now(job.id)
    await recorder.wait()
    await asyncio.sleep(0.3)
    after = await scheduler.get(job.id)
    assert after is not None
    assert after.when == tomorrow
    assert after.retry_at is None


# --- HANDLERS AND LIFECYCLE -------------------------------------------------------------------------------------------


async def test_jobs_wait_for_their_handler(make_scheduler: Any) -> None:
    scheduler = await started(make_scheduler)
    await scheduler.schedule("ping", utcnow())
    await asyncio.sleep(0.4)

    recorder = Recorder()
    scheduler.register(HandlerSpec(kind="ping", func=recorder))
    await recorder.wait(within=2)


async def test_unfinished_jobs_of_a_dead_process_run_after_start(make_scheduler: Any, pool: Any) -> None:
    first = make_scheduler()
    await first.install()
    job = await first.schedule("ping", utcnow())
    # pretend a process claimed the job and died
    await pool.execute("UPDATE scheduled_jobs SET claimed_at = NOW() WHERE id = $1", job.id)

    recorder = Recorder()
    await started(make_scheduler, HandlerSpec(kind="ping", func=recorder))
    await recorder.wait(within=2)


async def test_close_releases_waiting_jobs(make_scheduler: Any, pool: Any) -> None:
    scheduler = await started(make_scheduler, HandlerSpec(kind="ping", func=Recorder()))
    job = await scheduler.schedule("ping", utcnow() + dt.timedelta(seconds=0.35))
    await asyncio.sleep(0.15)
    assert await pool.fetchval("SELECT claimed_at FROM scheduled_jobs WHERE id = $1", job.id) is not None

    await scheduler.close()
    assert await pool.fetchval("SELECT claimed_at FROM scheduled_jobs WHERE id = $1", job.id) is None


async def test_close_waits_for_running_handlers(make_scheduler: Any, pool: Any) -> None:
    finished = asyncio.Event()

    async def slow(job: Job) -> None:
        await asyncio.sleep(0.3)
        finished.set()

    scheduler = await started(make_scheduler, HandlerSpec(kind="slow", func=slow))
    await scheduler.schedule("slow", utcnow())
    await asyncio.sleep(0.15)
    await scheduler.close(grace_period=2)
    assert finished.is_set()
    assert await row_count(pool) == 0


async def test_unknown_timezone_is_rejected(make_scheduler: Any) -> None:
    scheduler = make_scheduler()
    await scheduler.install()
    with pytest.raises(KeyError):
        await scheduler.schedule("x", WallTime(dt.datetime(2030, 1, 1), "Not/AZone"))


async def test_running_job_cannot_be_changed(make_scheduler: Any) -> None:
    started_event, release = asyncio.Event(), asyncio.Event()

    async def slow(job: Job) -> None:
        started_event.set()
        await release.wait()

    scheduler = await started(make_scheduler, HandlerSpec(kind="slow", func=slow))
    job = await scheduler.schedule("slow", utcnow())
    async with asyncio.timeout(3):
        await started_event.wait()
    assert await scheduler.update(job.id, data={"x": 1}) is None
    assert await scheduler.run_now(job.id) is None
    release.set()
