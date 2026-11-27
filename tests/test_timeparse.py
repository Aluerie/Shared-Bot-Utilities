# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
# ruff: file-ignore[call-datetime-without-tzinfo]  # wall times are naive on purpose
"""Tests for `shared.timeparse`: times users type in, and splitting them from chat text."""

import datetime as dt
import zoneinfo

import pytest

from shared import errors
from shared.scheduler import WallTime
from shared.timeparse import describe, describe_rule, parse_time, split_time

BERLIN = "Europe/Berlin"
NOW = dt.datetime(2026, 11, 26, 19, 30, tzinfo=dt.UTC)
"""Thursday, 20:30 in Berlin."""


@pytest.mark.parametrize(
    ("text", "berlin_time", "kind"),
    [
        ("2h30m", dt.datetime(2026, 11, 26, 23, 0), "absolute"),
        ("in 2 hours", dt.datetime(2026, 11, 26, 22, 30), "absolute"),
        ("90m", dt.datetime(2026, 11, 26, 22, 0), "absolute"),
        ("1d 2h", dt.datetime(2026, 11, 27, 22, 30), "absolute"),
        ("3 days", dt.datetime(2026, 11, 29, 20, 30), "wall"),
        ("2 weeks and 3 days", dt.datetime(2026, 12, 13, 20, 30), "wall"),
        ("tomorrow 3pm", dt.datetime(2026, 11, 27, 15, 0), "wall"),
        ("next friday 3pm", dt.datetime(2026, 11, 27, 15, 0), "wall"),
        ("friday", dt.datetime(2026, 11, 27, 20, 30), "wall"),  # the current time of day, not midnight
        ("15:00", dt.datetime(2026, 11, 27, 15, 0), "wall"),  # already passed today: tomorrow
        ("eod", dt.datetime(2026, 11, 26, 23, 59), "wall"),
        ("eow", dt.datetime(2026, 11, 27, 23, 59), "wall"),
        ("eom", dt.datetime(2026, 11, 30, 23, 59), "wall"),
        ("eoy", dt.datetime(2026, 12, 31, 23, 59), "wall"),
        ("2026-12-03 10:00", dt.datetime(2026, 12, 3, 10, 0), "wall"),  # ISO is year-month-day, not day-first
        ("2026-12-03", dt.datetime(2026, 12, 3, 20, 30), "wall"),
        ("03/04", dt.datetime(2027, 4, 3, 20, 30), "wall"),  # other dates are day-first
    ],
)
def test_parse_time(text: str, berlin_time: dt.datetime, kind: str) -> None:
    parsed = parse_time(text, now=NOW, timezone=BERLIN)
    assert parsed.when.to_utc() == parsed.moment
    assert parsed.moment == berlin_time.replace(tzinfo=zoneinfo.ZoneInfo(BERLIN)).astimezone(dt.UTC)
    assert parsed.is_absolute is (kind == "absolute")


def test_explicit_offset_wins_over_the_timezone() -> None:
    parsed = parse_time("2026-12-03T10:00+03:00", now=NOW, timezone=BERLIN)
    assert parsed.is_absolute
    assert parsed.moment == dt.datetime(2026, 12, 3, 7, 0, tzinfo=dt.UTC)


def test_discord_timestamp() -> None:
    parsed = parse_time("<t:1800000000:R>", now=NOW, timezone=BERLIN)
    assert parsed.moment == dt.datetime.fromtimestamp(1800000000, tz=dt.UTC)


@pytest.mark.parametrize("text", ["yesterday", "asdf", "", "   ", "9999 years"])
def test_bad_times_are_refused(text: str) -> None:
    with pytest.raises(errors.BadUserInputError):
        parse_time(text, now=NOW, timezone=BERLIN)


def test_describe() -> None:
    parsed = parse_time("tomorrow 3pm", now=NOW, timezone=BERLIN)
    assert describe(parsed, now=NOW, timezone=BERLIN) == "Fri 27 Nov 2026, 15:00 CET (in 18 hours 30 minutes)"
    assert describe(parse_time("1h", now=NOW), now=NOW).endswith("20:30 UTC (in 1 hour)")


# --- TIMEZONES IN THE INPUT -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "zone", "local"),
    [
        ("18:00 MSK", "Europe/Moscow", dt.datetime(2026, 11, 27, 18, 0)),  # 22:30 in Moscow now: tomorrow
        ("3pm est", "America/New_York", dt.datetime(2026, 11, 26, 15, 0)),  # 14:30 in New York now: later today
        ("tomorrow 9am CET", "Europe/Berlin", dt.datetime(2026, 11, 27, 9, 0)),
        ("friday 10:00 Europe/London", "Europe/London", dt.datetime(2026, 11, 27, 10, 0)),
        ("9am utc+3", "Etc/GMT-3", dt.datetime(2026, 11, 27, 9, 0)),  # IANA's Etc/GMT signs are inverted
        ("9am GMT-5", "Etc/GMT+5", dt.datetime(2026, 11, 27, 9, 0)),
        ("18:00 UTC", "UTC", dt.datetime(2026, 11, 26, 18, 0) + dt.timedelta(days=1)),
    ],
)
def test_timezone_in_the_input_wins(text: str, zone: str, local: dt.datetime) -> None:
    parsed = parse_time(text, now=NOW, timezone=BERLIN)
    assert parsed.when.timezone == zone
    assert parsed.when.local == local


def test_offsets_are_really_ahead_or_behind() -> None:
    ahead = parse_time("9am utc+3", now=NOW, timezone=BERLIN)
    assert ahead.moment == dt.datetime(2026, 11, 27, 6, 0, tzinfo=dt.UTC)
    behind = parse_time("9am gmt-5", now=NOW, timezone=BERLIN)
    assert behind.moment == dt.datetime(2026, 11, 27, 14, 0, tzinfo=dt.UTC)


def test_describe_shows_the_zone_that_was_typed() -> None:
    parsed = parse_time("18:00 MSK", now=NOW)
    assert describe(parsed, now=NOW).startswith("Fri 27 Nov 2026, 18:00 MSK (in ")


@pytest.mark.parametrize("text", ["9am utc+5:30", "9am utc+15"])
def test_odd_offsets_are_refused(text: str) -> None:
    with pytest.raises(errors.BadUserInputError, match="whole-hour"):
        parse_time(text, now=NOW)


def test_durations_ignore_timezones() -> None:
    with pytest.raises(errors.BadUserInputError, match="only goes with a clock time"):
        parse_time("1h ist", now=NOW)


# --- SPLITTING CHAT INPUT ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "time_text", "rest"),
    [
        ("10m stretch", "10m", "stretch"),
        ("10m", "10m", ""),
        ("in 2 hours drink water", "in 2 hours", "drink water"),
        ("tomorrow 3pm water the plants", "tomorrow 3pm", "water the plants"),
        ("next friday 3pm call mom", "next friday 3pm", "call mom"),
        ("eow to send the report", "eow", "send the report"),
        ("1h to may the force be with you", "1h", "may the force be with you"),
        ("2h30m that the pizza is ready", "2h30m", "the pizza is ready"),
        ("18:00 MSK stretch", "18:00 MSK", "stretch"),
        ("me 18:00 MSK stretch", "18:00 MSK", "stretch"),
        ("1h ist cool", "1h", "ist cool"),
    ],
)
def test_split_time(text: str, time_text: str, rest: str) -> None:
    parsed, remaining = split_time(text, now=NOW, timezone=BERLIN)
    assert parsed == parse_time(time_text, now=NOW, timezone=BERLIN)
    assert remaining == rest


def test_split_time_needs_a_time_first() -> None:
    with pytest.raises(errors.BadUserInputError, match="Start with a time"):
        split_time("stretch in 10m", now=NOW, timezone=BERLIN)


def test_split_time_reports_past_times() -> None:
    with pytest.raises(errors.BadUserInputError, match="in the past"):
        split_time("yesterday stretch", now=NOW, timezone=BERLIN)


# --- REPEATS ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "rule", "local"),
    [
        ("every day 9am", "FREQ=DAILY", dt.datetime(2026, 11, 27, 9, 0)),
        ("daily at 18:00", "FREQ=DAILY", dt.datetime(2026, 11, 27, 18, 0)),
        ("every weekday 8:30", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", dt.datetime(2026, 11, 27, 8, 30)),
        ("every weekend 11am", "FREQ=WEEKLY;BYDAY=SA,SU", dt.datetime(2026, 11, 28, 11, 0)),
        ("every friday 18:00", "FREQ=WEEKLY;BYDAY=FR", dt.datetime(2026, 11, 27, 18, 0)),
        ("every mon and thu 20:00", "FREQ=WEEKLY;BYDAY=MO,TH", dt.datetime(2026, 11, 30, 20, 0)),
        ("every thursdays, mondays at 8pm", "FREQ=WEEKLY;BYDAY=MO,TH", dt.datetime(2026, 11, 30, 20, 0)),
        ("every 2 weeks on friday 18:00", "FREQ=WEEKLY;INTERVAL=2;BYDAY=FR", dt.datetime(2026, 11, 27, 18, 0)),
        ("every month on the 15th 10:00", "FREQ=MONTHLY;BYMONTHDAY=15", dt.datetime(2026, 12, 15, 10, 0)),
        ("every day noon", "FREQ=DAILY", dt.datetime(2026, 11, 27, 12, 0)),
    ],
)
def test_repeats(text: str, rule: str, local: dt.datetime) -> None:
    parsed = parse_time(text, now=NOW, timezone=BERLIN)
    assert parsed.rule == rule
    assert parsed.when == WallTime(local, BERLIN)


def test_hourly_repeats_are_absolute() -> None:
    parsed = parse_time("every 3 hours", now=NOW, timezone=BERLIN)
    assert parsed.rule == "FREQ=HOURLY;INTERVAL=3"
    assert parsed.is_absolute
    assert parsed.moment == NOW + dt.timedelta(hours=3)


def test_repeats_with_a_timezone() -> None:
    parsed = parse_time("every friday 18:00 MSK", now=NOW, timezone=BERLIN)
    assert parsed.when == WallTime(dt.datetime(2026, 11, 27, 18, 0), "Europe/Moscow")


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("every 5 minutes", "at most every hour"),
        ("every blah", "couldn't understand the repeat"),
        ("every day 25:00", "time of day"),
        ("every 2 hours at 9am", "can't have a time of day"),
    ],
)
def test_bad_repeats(text: str, error: str) -> None:
    with pytest.raises(errors.BadUserInputError, match=error):
        parse_time(text, now=NOW, timezone=BERLIN)


@pytest.mark.parametrize(
    ("rule", "words"),
    [
        ("FREQ=DAILY", "every day"),
        ("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", "every weekday"),
        ("FREQ=WEEKLY;BYDAY=MO,TH", "every Mon and Thu"),
        ("FREQ=WEEKLY;INTERVAL=2;BYDAY=FR", "every 2 weeks on Fri"),
        ("FREQ=MONTHLY;BYMONTHDAY=22", "every month on the 22nd"),
        ("FREQ=HOURLY;INTERVAL=3", "every 3 hours"),
        ("FREQ=YEARLY", "every year"),
    ],
)
def test_describe_rule(rule: str, words: str) -> None:
    assert describe_rule(rule) == words


def test_split_repeats_from_chat() -> None:
    parsed, rest = split_time("every friday 18:00 water the plants", now=NOW, timezone=BERLIN)
    assert parsed.rule == "FREQ=WEEKLY;BYDAY=FR"
    assert rest == "water the plants"
    assert describe(parsed, now=NOW, timezone=BERLIN).startswith("every Fri, first: Fri 27 Nov 2026, 18:00 CET")
