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
import functools
import re
import zoneinfo
from dataclasses import dataclass
from typing import Final

from dateutil.relativedelta import relativedelta
lazy import dateparser

from . import clock, errors
from .scheduler import UTC, WallTime, recurrence

__all__ = (
    "ParsedTime",
    "describe",
    "describe_rule",
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

TIMEZONE_ABBREVIATIONS: Final = {
    # Abbreviations stand for the zone people mean all year: "EST" in July still means New York's time.
    # Ambiguous ones go to their most common meaning (IST: India, CST: US Central), and GMT is taken as UTC.
    "utc": "UTC",
    "gmt": "UTC",
    "wet": "Europe/Lisbon",
    "west": "Europe/Lisbon",
    "bst": "Europe/London",
    "cet": "Europe/Berlin",
    "cest": "Europe/Berlin",
    "eet": "Europe/Kyiv",
    "eest": "Europe/Kyiv",
    "msk": "Europe/Moscow",
    "ist": "Asia/Kolkata",
    "jst": "Asia/Tokyo",
    "kst": "Asia/Seoul",
    "awst": "Australia/Perth",
    "aest": "Australia/Sydney",
    "aedt": "Australia/Sydney",
    "nzst": "Pacific/Auckland",
    "nzdt": "Pacific/Auckland",
    "brt": "America/Sao_Paulo",
    "et": "America/New_York",
    "est": "America/New_York",
    "edt": "America/New_York",
    "ct": "America/Chicago",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "mt": "America/Denver",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "pt": "America/Los_Angeles",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "akst": "America/Anchorage",
    "akdt": "America/Anchorage",
    "hst": "Pacific/Honolulu",
}
"""Timezone abbreviations users may add to a time ("18:00 MSK"), and the IANA zones they stand for."""
_ZONE_ABBREVIATION: Final = re.compile(
    r"(?<![\w/])(" + "|".join(sorted(TIMEZONE_ABBREVIATIONS, key=len, reverse=True)) + r")(?![\w/])"
)
_ZONE_OFFSET: Final = re.compile(
    r"(?<![\w/])(?:utc|gmt)\s*(?P<sign>[+-])\s*(?P<hours>\d{1,2})(?::?(?P<minutes>\d{2}))?(?!\w)"
)
_ZONE_KEY: Final = re.compile(r"(?<![\w/])[a-z]+(?:/[a-z0-9_+-]+)+(?![\w/])")
MAX_OFFSET_HOURS: Final = 14


@dataclass(frozen=True, slots=True)
class ParsedTime:
    """A time a user typed in.

    Attributes
    ----------
    when
        What to schedule: an absolute (UTC) or a local wall time. For repeats, the first occurrence.
    moment
        The moment it stands for now (aware, UTC), for display.
    rule
        RRULE of a repeat ("every friday 18:00"), `None` for a one-off time.
    """

    when: WallTime
    moment: dt.datetime
    rule: str | None = None

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


@functools.cache
def _iana_keys() -> dict[str, str]:
    """IANA timezone keys by their lowercase form, to find "europe/berlin" typed in any case."""
    return {key.lower(): key for key in zoneinfo.available_timezones()}


def _extract_timezone(text: str) -> tuple[str, str] | None:
    """Find a timezone in lowercase input: an offset ("utc+3"), an IANA key ("europe/berlin") or "msk"-like names.

    Returns
    -------
    tuple[str, str] | None
        The IANA key of the zone and the text without it, or `None` if the text names no zone.

    Raises
    ------
    errors.BadUserInputError
        For offsets that aren't whole hours or are out of range.
    """
    if match := _ZONE_OFFSET.search(text):
        hours, minutes = int(match["hours"]), int(match["minutes"] or 0)
        if minutes or hours > MAX_OFFSET_HOURS:
            msg = 'Only whole-hour offsets like "UTC+3" work; for others name the zone, e.g. "IST" or "Asia/Kolkata".'
            raise errors.BadUserInputError(msg)
        # IANA's "Etc/GMT" zones have the sign the other way around: UTC+3 is "Etc/GMT-3"
        zone = "UTC" if hours == 0 else f"Etc/GMT{'-' if match['sign'] == '+' else '+'}{hours}"
    elif (match := _ZONE_KEY.search(text)) and (key := _iana_keys().get(match[0])) is not None:
        zone = key
    elif match := _ZONE_ABBREVIATION.search(text):
        zone = TIMEZONE_ABBREVIATIONS[match[1]]
    else:
        return None
    rest = " ".join((text[: match.start()] + " " + text[match.end() :]).split())
    return zone, rest


def _parse_iso(text: str) -> dt.datetime | dt.date | None:
    try:
        return dt.date.fromisoformat(text) if len(text) == 10 else dt.datetime.fromisoformat(text)
    except ValueError:
        return None


# --- REPEATS ----------------------------------------------------------------------------------------------------------

_DAY_CODES: Final = {
    "monday": "MO", "mon": "MO",
    "tuesday": "TU", "tue": "TU", "tues": "TU",
    "wednesday": "WE", "wed": "WE",
    "thursday": "TH", "thu": "TH", "thur": "TH", "thurs": "TH",
    "friday": "FR", "fri": "FR",
    "saturday": "SA", "sat": "SA",
    "sunday": "SU", "sun": "SU",
}  # fmt: skip
_DAY_NAMES: Final = {"MO": "Mon", "TU": "Tue", "WE": "Wed", "TH": "Thu", "FR": "Fri", "SA": "Sat", "SU": "Sun"}
_FREQUENCIES: Final = {"hour": "HOURLY", "day": "DAILY", "week": "WEEKLY", "month": "MONTHLY", "year": "YEARLY"}
_ALIASES: Final = {
    "hourly": "every hour",
    "daily": "every day",
    "weekly": "every week",
    "monthly": "every month",
    "yearly": "every year",
    "annually": "every year",
}
_DAY_WORD: Final = "|".join(sorted((*_DAY_CODES, *(f"{day}s" for day in _DAY_CODES)), key=len, reverse=True))
_DAY_LIST: Final = rf"(?:{_DAY_WORD})(?:\s*(?:,|and|&|\s)\s*(?:{_DAY_WORD}))*"
_REPEAT: Final = re.compile(
    rf"""
    every\s+
    (?:
        (?P<weekdays>weekdays?|workdays?)
      | (?P<weekend>weekends?)
      | (?P<days>{_DAY_LIST})
      | (?:(?P<interval>\d{{1,3}})\s+)?(?P<unit>hour|day|week|month|year)s?
        (?:\s+on\s+(?:(?P<on_days>{_DAY_LIST})|the\s+(?P<monthday>\d{{1,2}})(?:st|nd|rd|th)?))?
    )
    (?:\s+(?:at\s+)?(?P<time>.+))?
    """,
    re.VERBOSE,
)
_CLOCK: Final = re.compile(r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm|a\.m\.|p\.m\.)?")
LAST_HOUR: Final = 23
LAST_MINUTE: Final = 59
HALF_DAY_HOURS: Final = 12
LAST_MONTH_DAY: Final = 31
MIN_REPEAT_INTERVAL: Final = dt.timedelta(hours=1)
"""Repeats can't be more often than this: minute-long ones would be spam."""


def _day_codes(text: str) -> list[str]:
    words = re.findall(_DAY_WORD, text)
    codes = [_DAY_CODES[word.removesuffix("s") if word.removesuffix("s") in _DAY_CODES else word] for word in words]
    return sorted(set(codes), key=list(_DAY_NAMES).index)


def _clock_time(text: str, default: dt.time) -> dt.time:
    """Read a time of day: "9am", "18:00", "8:30 pm", "noon", "midnight"; empty is `default`."""
    text = text.strip()
    if not text:
        return default
    if text in {"noon", "midday"}:
        return dt.time(12)
    if text == "midnight":
        return dt.time(0)
    match = _CLOCK.fullmatch(text)
    if match is None:
        msg = f'I couldn\'t understand the time of day {text!r}, try e.g. "9am" or "18:00".'
        raise errors.BadUserInputError(msg)
    hour, minute = int(match["hour"]), int(match["minute"] or 0)
    if ampm := match["ampm"]:
        if not 1 <= hour <= HALF_DAY_HOURS:
            msg = f"{text!r} isn't a time of day."
            raise errors.BadUserInputError(msg)
        hour = hour % HALF_DAY_HOURS + (HALF_DAY_HOURS if ampm.startswith("p") else 0)
    if hour > LAST_HOUR or minute > LAST_MINUTE:
        msg = f"{text!r} isn't a time of day."
        raise errors.BadUserInputError(msg)
    return dt.time(hour, minute)


def _parse_repeat(text: str, *, now: dt.datetime, timezone: str) -> ParsedTime | None:
    """Understand "every friday 18:00"-like input; `None` if it isn't a repeat."""
    for alias, meaning in _ALIASES.items():
        if text == alias or text.startswith(f"{alias} "):
            text = meaning + text.removeprefix(alias)
            break
    if not text.startswith("every "):
        return None
    if (found := _extract_timezone(text)) is not None:
        timezone, text = found
    match = _REPEAT.fullmatch(text)
    if match is None:
        if re.match(r"every\s+(?:\d+\s+)?(?:minute|min|second|sec)", text):
            msg = "Reminders can repeat at most every hour."
            raise errors.BadUserInputError(msg)
        msg = (
            f"I couldn't understand the repeat {text!r}. "
            'Try e.g. "every day 9am", "every friday 18:00", "every mon and thu 20:00", "every 2 weeks on friday".'
        )
        raise errors.BadUserInputError(msg)

    local_now = now.astimezone(zoneinfo.ZoneInfo(timezone)).replace(tzinfo=None, microsecond=0)
    parts: list[str]
    if match["weekdays"]:
        parts = ["FREQ=WEEKLY", "BYDAY=MO,TU,WE,TH,FR"]
    elif match["weekend"]:
        parts = ["FREQ=WEEKLY", "BYDAY=SA,SU"]
    elif match["days"]:
        parts = ["FREQ=WEEKLY", f"BYDAY={','.join(_day_codes(match['days']))}"]
    else:
        parts = [f"FREQ={_FREQUENCIES[match['unit']]}"]
        if (interval := int(match["interval"] or 1)) > 1:
            parts.append(f"INTERVAL={interval}")
        if match["on_days"]:
            parts.append(f"BYDAY={','.join(_day_codes(match['on_days']))}")
        if match["monthday"]:
            if not 1 <= int(match["monthday"]) <= LAST_MONTH_DAY:
                msg = f"There's no {match['monthday']}th day of a month."
                raise errors.BadUserInputError(msg)
            parts.append(f"BYMONTHDAY={int(match['monthday'])}")
    rule = ";".join(parts)

    if match["unit"] == "hour":
        # hours are real hours, the same across DST changes: the repeat is absolute, from now
        if match["time"]:
            msg = 'Hourly repeats start now, they can\'t have a time of day: try just "every 2 hours".'
            raise errors.BadUserInputError(msg)
        first = _absolute(now + dt.timedelta(hours=int(match["interval"] or 1)))
        return ParsedTime(first.when, first.moment, rule=rule)

    time_of_day = _clock_time(match["time"] or "", default=local_now.time())
    start = dt.datetime.combine(local_now.date(), time_of_day)
    first_local = recurrence.next_occurrence(rule, current=start, after=local_now)
    if first_local is None:  # can't happen for rules without UNTIL, but a clear error beats an assert
        msg = f"The repeat {text!r} never happens."
        raise errors.BadUserInputError(msg)
    first = _wall(first_local, timezone)
    return ParsedTime(first.when, first.moment, rule=rule)


def describe_rule(rule: str) -> str:
    """Describe a repeat rule in words: "every day", "every Mon and Thu", "every 2 weeks on Fri", "every hour".

    Rules that this module doesn't make are described as they are.
    """
    fields = dict(part.split("=", 1) for part in rule.split(";") if "=" in part)
    unit = {value: key for key, value in _FREQUENCIES.items()}.get(fields.get("FREQ", ""))
    if unit is None:
        return rule
    interval = int(fields.get("INTERVAL", "1"))
    text = f"every {interval} {unit}s" if interval > 1 else f"every {unit}"
    if (days := fields.get("BYDAY")) is not None:
        codes = days.split(",")
        names = (
            "weekday"
            if codes == ["MO", "TU", "WE", "TH", "FR"]
            else "weekend day"
            if codes == ["SA", "SU"]
            else " and ".join(_DAY_NAMES.get(code, code) for code in codes)
        )
        text = f"every {names}" if unit == "week" and interval == 1 else f"{text} on {names}"
    if (monthday := fields.get("BYMONTHDAY")) is not None:
        text += f" on the {monthday}{_ordinal_suffix(int(monthday))}"
    return text


def _ordinal_suffix(number: int) -> str:
    teens = range(11, 14)  # 11th, 12th, 13th
    if number % 100 in teens:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")


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

    if (repeat := _parse_repeat(lowered, now=now, timezone=timezone)) is not None:
        return repeat

    if (found := _extract_timezone(lowered)) is not None:
        zone, rest = found
        if not rest or _parse_duration(rest) is not None:
            # "1h ist": durations don't depend on a timezone, so the word is something else
            msg = f'I couldn\'t understand the time {raw!r}: a timezone only goes with a clock time, like "18:00 MSK".'
            raise errors.BadUserInputError(msg)
        # a zone in the input wins over the user's timezone: "18:00 MSK" is 18:00 on Moscow's clocks
        timezone, lowered = zone, rest
        local_now = now.astimezone(zoneinfo.ZoneInfo(timezone)).replace(tzinfo=None)

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
        A clock time can name its timezone, which then wins over `timezone`: "18:00 MSK", "3pm EST",
        "friday 10:00 Europe/Berlin", "9am UTC+3".
        Repeats give a `ParsedTime` with a `rule` and their first occurrence: "every day 9am", "every friday 18:00",
        "every mon and thu 20:00", "every weekday 8:30", "every 2 weeks on friday", "every month on the 15th 10:00",
        "every 3 hours" (real hours, from now), "daily", "weekly".
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
    if words and words[0].lower() == "me":  # "!remind me 18:00 MSK ..."
        words = words[1:]
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

    Clock times are shown on the clocks they were given for (the user's, or the zone typed in, like "18:00 MSK");
    absolute times on the user's clocks.

    Returns
    -------
    str
        Like "Fri 27 Nov 2026, 15:00 CET (in 18 hours)".
    """
    shown = timezone if parsed.when.is_absolute else parsed.when.timezone
    local = parsed.moment.astimezone(zoneinfo.ZoneInfo(shown))
    relative = clock.human_datetime_diff(parsed.moment, relative_to=now, max_units=2)
    when = "in " + relative if parsed.moment > now else relative + " ago"
    text = f"{local:%a %d %b %Y, %H:%M %Z} ({when})"
    if parsed.rule is not None:
        return f"{describe_rule(parsed.rule)}, first: {text}"
    return text
