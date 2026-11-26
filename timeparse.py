# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Times that users type in: "2h30m", "tomorrow 3pm", "eow", "2026-12-03 10:00", ``<t:1700000000:R>``.

Every input is understood in the user's timezone and becomes one of two things:

* an absolute time ("in 2 hours", "90m", Discord timestamps, ISO times with an offset): a fixed moment,
  the same however the clocks change in between;
* a wall time ("tomorrow 3pm", "in 3 days", "friday"): a time on the user's clocks, so it still fires at 3pm
  even if the clocks change (DST) before it.

Both kinds are `WallTime`s (absolute ones in UTC), ready for `shared.scheduler`.
"""

import datetime as dt
import re
import zoneinfo
from dataclasses import dataclass
from typing import Final

from dateutil.relativedelta import relativedelta
lazy import dateparser

from . import clock, errors
from .scheduler import UTC, WallTime

__all__ = (
    "ParsedTime",
    "describe",
    "parse_time",
    "split_time",
)

MAX_FUTURE: Final = dt.timedelta(days=366 * 20)
"""Times further than this are refused: nobody means them, and very far dates break things."""
MAX_TIME_WORDS: Final = 6
"""`split_time` looks for the time in at most this many first words."""
JOINERS: Final = frozenset({"to", "that", "about"})
"""Words between the time and the text in chat ("in 1h to stretch"); they end the time and are dropped."""

DISCORD_TIMESTAMP: Final = re.compile(r"<t:(?P<ts>-?\d{1,13})(?::[tTdDfFsSR])?>")

_UNITS: Final = {
    "years": ("y", "yr", "yrs", "year", "years"),
    "months": ("mo", "mon", "month", "months"),
    "weeks": ("w", "wk", "wks", "week", "weeks"),
    "days": ("d", "day", "days"),
    "hours": ("h", "hr", "hrs", "hour", "hours"),
    "minutes": ("m", "min", "mins", "minute", "minutes"),
    "seconds": ("s", "sec", "secs", "second", "seconds"),
}
_UNIT_LOOKUP: Final = {alias: unit for unit, aliases in _UNITS.items() for alias in aliases}
_DURATION_PART: Final = re.compile(
    # `(?![a-z])` rather than `\b`: "2h30m" has no word boundary between "h" and "3"
    r"(?P<amount>\d{1,6})\s*(?P<unit>" + "|".join(sorted(_UNIT_LOOKUP, key=len, reverse=True)) + r")(?![a-z])"
)
_DURATION: Final = re.compile(rf"(?:in\s+)?(?:{_DURATION_PART.pattern}\s*(?:,|and)?\s*)+")
ABSOLUTE_UNITS: Final = frozenset({"hours", "minutes", "seconds"})
"""Durations with these units are absolute ("in 2 hours" is 2 real hours); whole days and longer follow the clocks."""

_WEEKDAYS: Final = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_NEXT_WEEKDAY: Final = re.compile(rf"\bnext\s+({'|'.join(_WEEKDAYS)})\b")
_HAS_TIME: Final = re.compile(r"\d\s*(?:am|pm|a\.m\.|p\.m\.)|\d:\d|\b(?:noon|midnight|morning|evening|night)\b")
END_OF_DAY: Final = dt.time(23, 59)
TONIGHT: Final = dt.time(20, 0)


@dataclass(frozen=True, slots=True)
class ParsedTime:
    """A time a user typed in.

    Attributes
    ----------
    when
        What to schedule: an absolute (UTC) or a local wall time.
    moment
        The moment it stands for now (aware, UTC), for display.
    """

    when: WallTime
    moment: dt.datetime

    @property
    def is_absolute(self) -> bool:
        """Whether this is a fixed moment ("in 2 hours") rather than a time on the user's clocks ("at 3pm")."""
        return self.when.is_absolute


def _absolute(moment: dt.datetime) -> ParsedTime:
    wall = WallTime.from_aware(moment)
    return ParsedTime(wall, wall.to_utc())


def _wall(local: dt.datetime, timezone: str) -> ParsedTime:
    wall = WallTime(local.replace(tzinfo=None), timezone)
    return ParsedTime(wall, wall.to_utc())


def _parse_duration(text: str) -> relativedelta | None:
    if _DURATION.fullmatch(text) is None:
        return None
    amounts: dict[str, int] = {}
    for match in _DURATION_PART.finditer(text):
        unit = _UNIT_LOOKUP[match["unit"]]
        amounts[unit] = amounts.get(unit, 0) + int(match["amount"])
    return relativedelta(**amounts)


def _end_of(keyword: str, local_now: dt.datetime) -> dt.datetime | None:
    today = local_now.date()
    match keyword:
        case "eod":
            date = today
        case "tonight":
            return dt.datetime.combine(today, TONIGHT)
        case "eow":  # the end of the working week: Friday
            date = today + dt.timedelta(days=(4 - today.weekday()) % 7)
        case "eom":
            date = today + relativedelta(day=31)
        case "eoy":
            date = today.replace(month=12, day=31)
        case _:
            return None
    return dt.datetime.combine(date, END_OF_DAY)


def _parse_iso(text: str) -> dt.datetime | dt.date | None:
    try:
        return dt.date.fromisoformat(text) if len(text) == 10 else dt.datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse(text: str, *, now: dt.datetime, timezone: str) -> ParsedTime:
    raw = " ".join(text.split())
    lowered = raw.lower()
    local_now = now.astimezone(zoneinfo.ZoneInfo(timezone)).replace(tzinfo=None)

    if match := DISCORD_TIMESTAMP.fullmatch(raw):
        try:
            return _absolute(dt.datetime.fromtimestamp(int(match["ts"]), tz=dt.UTC))
        except OverflowError, ValueError, OSError:
            msg = "That timestamp is out of range."
            raise errors.BadUserInputError(msg) from None

    if (iso := _parse_iso(raw)) is not None:
        if not isinstance(iso, dt.datetime):  # a date alone: keep the current time of day
            return _wall(dt.datetime.combine(iso, local_now.time()), timezone)
        if iso.tzinfo is not None:  # an explicit offset wins over the user's timezone
            return _absolute(iso)
        return _wall(iso, timezone)

    if (delta := _parse_duration(lowered)) is not None:
        units = {unit for unit in _UNITS if getattr(delta, unit)}
        try:
            if units & ABSOLUTE_UNITS:
                return _absolute(now + delta)
            return _wall(local_now + delta, timezone)
        except OverflowError, ValueError:
            msg = "That is too far away, please choose a closer time."
            raise errors.BadUserInputError(msg) from None

    if (end := _end_of(lowered, local_now)) is not None:
        return _wall(end, timezone)

    # dateparser doesn't understand "next friday", but "friday" (with future dates preferred) is the same
    cleaned = _NEXT_WEEKDAY.sub(r"\1", lowered)
    parsed = dateparser.parse(
        cleaned,
        languages=["en"],
        settings={
            "PREFER_DATES_FROM": "future",
            "RELATIVE_BASE": local_now,
            "DATE_ORDER": "DMY",
            "RETURN_AS_TIMEZONE_AWARE": False,
        },
    )
    if parsed is None:
        msg = (
            f"I couldn't understand the time {raw!r}. "
            'Try e.g. "2h30m", "tomorrow 3pm", "friday 18:00", "eow" or "2026-12-03 10:00".'
        )
        raise errors.BadUserInputError(msg)
    if _HAS_TIME.search(cleaned) is None and parsed.time() == dt.time():
        # "friday" alone: dateparser picks midnight, the current time of day is what people mean
        parsed = dt.datetime.combine(parsed.date(), local_now.time())
    return _wall(parsed, timezone)


def parse_time(text: str, *, now: dt.datetime, timezone: str = UTC) -> ParsedTime:
    """Understand a time that a user typed in, in their timezone. It must be in the future.

    Parameters
    ----------
    text
        The user's input: a duration ("2h30m", "in 3 days"), a keyword ("eod", "eow", "eom", "eoy", "tonight"),
        an ISO date/time (an offset in it wins over `timezone`), a Discord timestamp, or anything
        ``dateparser`` understands ("tomorrow 3pm", "friday", "3 december 10:00"). Dates are day-first.
    now
        The current moment (aware).
    timezone
        The user's IANA timezone.

    Raises
    ------
    errors.BadUserInputError
        If the input can't be understood or isn't in the future.
    """
    if not text.strip():
        msg = "Please tell me when."
        raise errors.BadUserInputError(msg)
    parsed = _parse(text, now=now, timezone=timezone)
    if parsed.moment <= now:
        msg = f"{describe(parsed, now=now, timezone=timezone)} is in the past."
        raise errors.BadUserInputError(msg)
    if parsed.moment - now > MAX_FUTURE:
        msg = "That is too far away, please choose a closer time."
        raise errors.BadUserInputError(msg)
    return parsed


def split_time(text: str, *, now: dt.datetime, timezone: str = UTC) -> tuple[ParsedTime, str]:
    """Split chat input like "tomorrow 3pm water the plants" into the time at its start and the rest.

    The time grows word by word while it still makes sense, and stops at the first word that breaks it
    or at a joiner ("to", "that", "about"), which is dropped: "in 1h to call mom" is "in 1h" + "call mom".

    Parameters
    ----------
    text
        The user's input: a time (see `parse_time`), then the text.
    now
        The current moment (aware).
    timezone
        The user's IANA timezone.

    Returns
    -------
    tuple[ParsedTime, str]
        The time and the rest of the text (may be empty).

    Raises
    ------
    errors.BadUserInputError
        If the input doesn't start with a time in the future.
    """
    words = text.split()
    best: tuple[ParsedTime, int] | None = None
    first_error: errors.BadUserInputError | None = None
    for count in range(1, min(len(words), MAX_TIME_WORDS) + 1):
        if words[count - 1].lower() in JOINERS:
            break
        try:
            best = parse_time(" ".join(words[:count]), now=now, timezone=timezone), count
        except errors.BadUserInputError as exc:
            first_error = first_error or exc
            if best is not None:
                break

    if best is None:
        if first_error is not None and "couldn't understand" not in str(first_error):
            raise first_error  # e.g. "in the past"
        msg = 'Start with a time, e.g. "10m stretch", "tomorrow 3pm water the plants" or "eow to send the report".'
        raise errors.BadUserInputError(msg)

    parsed, count = best
    rest = words[count:]
    if rest and rest[0].lower() in JOINERS:
        rest = rest[1:]
    return parsed, " ".join(rest)


def describe(parsed: ParsedTime, *, now: dt.datetime, timezone: str = UTC) -> str:
    """Describe a parsed time in plain text (for places without Discord timestamps, like autocomplete or chat).

    Returns
    -------
    str
        Like "Fri 27 Nov 2026, 15:00 (in 18 hours)", in the user's timezone.
    """
    local = parsed.moment.astimezone(zoneinfo.ZoneInfo(timezone))
    relative = clock.human_datetime_diff(parsed.moment, relative_to=now, max_units=2)
    when = "in " + relative if parsed.moment > now else relative + " ago"
    zone = " UTC" if timezone == UTC else ""
    return f"{local:%a %d %b %Y, %H:%M}{zone} ({when})"
