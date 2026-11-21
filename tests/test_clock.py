# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Tests for ``shared.clock``."""

import datetime as dt

import pytest

from shared import clock

ANCHOR = dt.datetime(2026, 1, 15, 12, 0, 0, tzinfo=dt.UTC)


def test_utcnow_is_aware_utc() -> None:
    assert clock.utcnow().tzinfo is dt.UTC


def test_get_next_hour_start_always_advances() -> None:
    assert clock.get_next_hour_start(ANCHOR) == ANCHOR + dt.timedelta(hours=1)
    assert clock.get_next_hour_start(ANCHOR.replace(minute=59, second=30)) == ANCHOR + dt.timedelta(hours=1)


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("full", "2 hours 1 minute 6 seconds"),
        ("short", "2 hrs 1 min 6 sec"),
        ("letter", "02h01m06s"),
    ],
)
def test_human_timedelta_modes(mode: clock.HumanTimedeltaMode, expected: str) -> None:
    assert clock.human_timedelta(dt.timedelta(hours=2, seconds=66), mode=mode, max_units=None) == expected


def test_human_timedelta_defaults_to_two_units() -> None:
    assert clock.human_timedelta(hours=2, seconds=66) == "2 hours 1 minute"


def test_human_timedelta_edge_cases() -> None:
    assert clock.human_timedelta(seconds=0) == "0 seconds"
    assert clock.human_timedelta(hours=-2) == "2 hours"  # sign is ignored
    assert clock.human_timedelta(days=500, max_units=1) == "500 days"  # nothing above days


def test_human_timedelta_argument_validation() -> None:
    with pytest.raises(TypeError):
        clock.human_timedelta()
    with pytest.raises(TypeError):
        clock.human_timedelta(dt.timedelta(1), hours=1)  # ty: ignore[no-matching-overload]
    with pytest.raises(ValueError, match="mode"):
        clock.human_timedelta(hours=1, mode="nope")  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValueError, match="max_units"):
        clock.human_timedelta(hours=1, max_units=0)


def test_human_datetime_diff_future_and_past() -> None:
    later = ANCHOR + dt.timedelta(days=9, hours=3)
    assert clock.human_datetime_diff(later, relative_to=ANCHOR) == "1 week 2 days"
    assert clock.human_datetime_diff(ANCHOR, relative_to=later, suffix=True) == "1 week 2 days ago"
    assert clock.human_datetime_diff(later, relative_to=ANCHOR, max_units=None) == "1 week 2 days 3 hours"


def test_human_datetime_diff_uses_calendar_months() -> None:
    assert clock.human_datetime_diff(ANCHOR.replace(year=2027, month=3), relative_to=ANCHOR) == "1 year 2 months"


def test_human_datetime_diff_treats_naive_as_utc() -> None:
    naive = ANCHOR.replace(tzinfo=None) + dt.timedelta(minutes=5)
    assert clock.human_datetime_diff(naive, relative_to=ANCHOR) == "5 minutes"


def test_discord_timestamps() -> None:
    timestamp = int(ANCHOR.timestamp())
    assert clock.discord(ANCHOR) == f"<t:{timestamp}:f>"
    assert clock.discord(ANCHOR, "R", "t") == f"<t:{timestamp}:R> <t:{timestamp}:t>"
