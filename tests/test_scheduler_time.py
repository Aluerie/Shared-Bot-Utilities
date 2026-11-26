# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
# ruff: file-ignore[call-datetime-without-tzinfo]  # wall times are naive on purpose
"""Tests for the scheduler's time logic: wall times, DST, repeat rules, handler registration."""

import datetime as dt
from typing import Any

import pytest

from shared.scheduler import (
    HandlerSpec,
    InvalidRuleError,
    Job,
    Scheduler,
    WallTime,
    handler,
    min_gap,
    next_occurrence,
    resolve,
    to_wall_time,
    validate_rule,
)

BERLIN = "Europe/Berlin"


# --- WALL TIME --------------------------------------------------------------------------------------------------------


def test_resolve_regular_time() -> None:
    assert resolve(dt.datetime(2026, 7, 1, 12), BERLIN) == dt.datetime(2026, 7, 1, 10, tzinfo=dt.UTC)


def test_resolve_skipped_time_matches_postgres() -> None:
    # 2026-03-29 02:30 doesn't exist in Berlin; PostgreSQL uses the offset from before the jump (+01:00)
    assert resolve(dt.datetime(2026, 3, 29, 2, 30), BERLIN) == dt.datetime(2026, 3, 29, 1, 30, tzinfo=dt.UTC)


def test_resolve_repeated_time_matches_postgres() -> None:
    # 2026-10-25 02:30 happens twice in Berlin; PostgreSQL takes the later one (+01:00)
    assert resolve(dt.datetime(2026, 10, 25, 2, 30), BERLIN) == dt.datetime(2026, 10, 25, 1, 30, tzinfo=dt.UTC)


def test_wall_time_rejects_aware_local() -> None:
    with pytest.raises(ValueError, match="naive"):
        WallTime(dt.datetime(2026, 1, 1, tzinfo=dt.UTC))


def test_wall_time_rejects_unknown_timezone() -> None:
    with pytest.raises(KeyError):
        WallTime(dt.datetime(2026, 1, 1), "Not/AZone")


def test_wall_time_from_aware_reads_the_local_clock() -> None:
    wall = WallTime.from_aware(dt.datetime(2026, 7, 1, 10, tzinfo=dt.UTC), BERLIN)
    assert wall == WallTime(dt.datetime(2026, 7, 1, 12), BERLIN)
    assert wall.to_utc() == dt.datetime(2026, 7, 1, 10, tzinfo=dt.UTC)
    assert not wall.is_absolute


def test_wall_time_addition_keeps_the_clock_time_across_dst() -> None:
    before = WallTime(dt.datetime(2026, 3, 28, 9), BERLIN)  # the day before clocks jump forward
    after = before + dt.timedelta(days=1)
    assert after.local == dt.datetime(2026, 3, 29, 9)
    assert after.to_utc() - before.to_utc() == dt.timedelta(hours=23)


def test_to_wall_time_keeps_absolute_moments_in_utc() -> None:
    moment = dt.datetime(2026, 7, 1, 10, tzinfo=dt.UTC)
    assert to_wall_time(moment).is_absolute
    assert to_wall_time(moment).to_utc() == moment


# --- REPEAT RULES -----------------------------------------------------------------------------------------------------


def test_daily_rule_keeps_local_clock_time_across_dst() -> None:
    current = dt.datetime(2026, 3, 28, 9)
    nxt = next_occurrence("FREQ=DAILY", current=current, after=current)
    assert nxt == dt.datetime(2026, 3, 29, 9)


def test_missed_occurrences_collapse_into_the_next_one() -> None:
    # the bot was down for three days: the next run is the first one after "now", not the three missed ones
    nxt = next_occurrence("FREQ=DAILY", current=dt.datetime(2026, 1, 1, 9), after=dt.datetime(2026, 1, 4, 10))
    assert nxt == dt.datetime(2026, 1, 5, 9)


def test_weekly_rule_with_days() -> None:
    monday = dt.datetime(2026, 11, 23, 18)
    assert next_occurrence("FREQ=WEEKLY;BYDAY=MO,FR", current=monday, after=monday) == dt.datetime(2026, 11, 27, 18)


def test_rule_with_until_ends() -> None:
    current = dt.datetime(2026, 1, 1, 9)
    assert next_occurrence("FREQ=DAILY;UNTIL=20260102T090000", current=current, after=current) is not None
    last = dt.datetime(2026, 1, 2, 9)
    assert next_occurrence("FREQ=DAILY;UNTIL=20260102T090000", current=last, after=last) is None


def test_validate_rule_rejects_count() -> None:
    with pytest.raises(InvalidRuleError, match="COUNT"):
        validate_rule("FREQ=DAILY;COUNT=3", dt.datetime(2026, 1, 1))


def test_validate_rule_rejects_garbage() -> None:
    with pytest.raises(InvalidRuleError):
        validate_rule("FREQ=SOMETIMES", dt.datetime(2026, 1, 1))


def test_validate_rule_rejects_rules_that_never_fire() -> None:
    with pytest.raises(InvalidRuleError, match="never fires"):
        validate_rule("FREQ=DAILY;UNTIL=20250101T000000", dt.datetime(2026, 1, 1))


def test_min_gap() -> None:
    start = dt.datetime(2026, 1, 1, 9)
    assert min_gap("FREQ=HOURLY;INTERVAL=2", start) == dt.timedelta(hours=2)
    assert min_gap("FREQ=WEEKLY;BYDAY=MO,TU", start) == dt.timedelta(days=1)


# --- HANDLERS ---------------------------------------------------------------------------------------------------------


class _Pool:
    """A pool that is never used: registration doesn't touch the database."""


class _Cog:
    @property
    def broken(self) -> Any:
        msg = "registration must not evaluate properties"
        raise AssertionError(msg)

    @handler("first", max_lateness=dt.timedelta(days=1))
    async def first(self, job: Job) -> None: ...

    @handler("second", max_attempts=5)
    async def second(self, job: Job) -> None: ...

    async def not_a_handler(self, job: Job) -> None: ...


async def test_register_handlers_of_an_object() -> None:
    scheduler = Scheduler(_Pool())  # ty: ignore[invalid-argument-type]
    cog = _Cog()
    assert sorted(scheduler.register_handlers(cog)) == ["first", "second"]
    assert sorted(scheduler.kinds) == ["first", "second"]

    scheduler.unregister_handlers(cog)
    assert scheduler.kinds == []


async def test_a_kind_has_one_handler() -> None:
    scheduler = Scheduler(_Pool())  # ty: ignore[invalid-argument-type]
    scheduler.register_handlers(_Cog())
    with pytest.raises(ValueError, match="already has a handler"):
        scheduler.register_handlers(_Cog())


def test_handler_spec_needs_an_attempt() -> None:
    async def func(job: Job) -> None: ...

    with pytest.raises(ValueError, match="max_attempts"):
        HandlerSpec(kind="x", func=func, max_attempts=0)
