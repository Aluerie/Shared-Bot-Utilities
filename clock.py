"""Time and datetime utilities.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

import datetime as dt
from typing import Literal, NamedTuple, assert_never, get_args, overload

from dateutil.relativedelta import relativedelta
from discord.utils import TimestampStyle, copy_doc, format_dt

from .fmt import plural

#############################################################################################################################
# GET TIME
#############################################################################################################################


def utcnow() -> dt.datetime:
    """Get an aware UTC dt.datetime representing the current time.

    Returns
    -------
    dt.datetime
        The current aware datetime in UTC.
    """
    return dt.datetime.now(dt.UTC)


def get_next_hour_start(when: dt.datetime) -> dt.datetime:
    """Get next hour start.

    This always advances. (e.g. 12:00:00 becomes 13:00:00)

    Source
    ------
    * https://stackoverflow.com/a/48108115

    Parameters
    ----------
    when
        Datetime object to round up. UTC expected.

    Returns
    -------
    dt.datetime
        The start of the next hour.
    """
    return when.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)


#############################################################################################################################
# HUMAN DATETIME DIFF AND TIMEDELTA
#############################################################################################################################


type HumanTimedeltaMode = Literal["full", "short", "letter"]


def _validate_mode(mode: str) -> None:
    valid_modes = get_args(HumanTimedeltaMode.__value__)
    if mode not in valid_modes:
        msg = f"`mode` should be one of {valid_modes}, got {mode!r}."
        raise ValueError(msg)


def _validate_max_units(max_units: int | None) -> None:
    if max_units is not None and max_units < 1:
        msg = "`max_units` should be at least 1 (or None for no limit)."
        raise ValueError(msg)


def _normalize_to_utc(when: dt.datetime) -> dt.datetime:
    """Return an aware, second-precision UTC datetime.

    * makes it timezone-aware (naive datetimes are assumed to be UTC);
    * removes microseconds;
    * converts to UTC timezone;
    """
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    when = when.replace(microsecond=0)
    return when.astimezone(dt.UTC)


type TimeUnitLiteral = Literal["years", "months", "weeks", "days", "hours", "minutes", "seconds"]


class _Unit(NamedTuple):
    attr: TimeUnitLiteral
    full: str  # "hour"
    short: str  # "hr"
    letter: str  # "h"
    plural_short: bool


_TIME_UNITS = (
    _Unit("years", "year", "year", "y", plural_short=True),
    _Unit("months", "month", "month", "mo", plural_short=True),
    _Unit("weeks", "week", "wk", "w", plural_short=True),
    _Unit("days", "day", "day", "d", plural_short=True),
    _Unit("hours", "hour", "hr", "h", plural_short=True),
    _Unit("minutes", "minute", "min", "m", plural_short=False),
    _Unit("seconds", "second", "sec", "s", plural_short=False),
)


def _format_part(amount: int, unit: _Unit, mode: HumanTimedeltaMode) -> str:
    match mode:
        case "full":
            return format(plural(amount), unit.full)
        case "short":
            return format(plural(amount), unit.short) if unit.plural_short else f"{amount} {unit.short}"
        case "letter":
            return f"{amount:02d}{unit.letter}"
        case _:
            assert_never(mode)


def _select_parts(amounts: dict[TimeUnitLiteral, int], mode: HumanTimedeltaMode, max_units: int | None) -> str:
    """Format ``amounts`` into a string, ordered from largest to smallest unit.

    Units missing from ``amounts`` are skipped.
    In "letter" mode, zeros after the first non-zero unit are kept (e.g. "01h00m05s").
    In other modes all zero units are dropped.
    """
    units = [u for u in _TIME_UNITS if u.attr in amounts]

    if mode == "letter":
        first = next((i for i, u in enumerate(units) if amounts[u.attr]), len(units))
        units = units[first:]
    else:
        units = [u for u in units if amounts[u.attr]]

    parts = [_format_part(amounts[u.attr], u, mode) for u in units][:max_units]
    if not parts:
        return {"full": "0 seconds", "short": "0 sec", "letter": "00s"}[mode]
    return ("" if mode == "letter" else " ").join(parts)


def human_datetime_diff(
    when: dt.datetime,
    *,
    relative_to: dt.datetime | None = None,
    max_units: int | None = 2,
    mode: HumanTimedeltaMode = "full",
    suffix: bool = False,
) -> str:
    """Convert ``when`` to a string of humanly readable words.

    Use this function when you need a difference between datetimes, e.g. dates.
    Supports units from years down to seconds.

    Source
    ------
    * licensed MPL v2 from Rapptz/RoboDanny
        https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/utils/time.py

    Parameters
    ----------
    when
        Datetime object. Naive datetimes are assumed UTC.
    relative_to
        Datetime source to compare against. Assumed as now if not given.
    max_units
        Amount of words to show in the result. Pass ``None`` for full accuracy.
        This truncates the output.
    mode
        Formatting choice for the output. See examples.
    suffix
        Optionally add suffix " ago" to past datetimes.

    Returns
    -------
    str
        Human-readable description for the datetime difference.

    Examples
    --------
    .. code-block:: python

        human_datetime_diff(when, mode="full")  # "2 hours 1 minute 6 seconds"
        human_datetime_diff(when, mode="short")  # "2 hrs 1 min 6 sec"
        human_datetime_diff(when, mode="letter")  # "02h01m06s"

    """
    _validate_mode(mode)
    _validate_max_units(max_units)

    anchor = _normalize_to_utc(relative_to or utcnow())
    when = _normalize_to_utc(when)

    # This implementation uses ``relativedelta`` instead of the much more obvious
    # divmod approach with seconds because the seconds approach is not entirely
    # accurate once you go over 1 week in terms of accuracy since you have to
    # hardcode a month as 30 or 31 days.
    # A query like "11 months" can be interpreted as "11 months and 6 days"
    if when >= anchor:
        rel_delta = relativedelta(when, anchor)
        output_suffix = ""
    else:
        rel_delta = relativedelta(anchor, when)
        output_suffix = " ago" if suffix else ""

    weeks, days = divmod(rel_delta.days, 7)  # `relativedelta` doesn't handle weeks the way I want
    amounts: dict[TimeUnitLiteral, int] = {
        "years": rel_delta.years,
        "months": rel_delta.months,
        "weeks": weeks,
        "days": days,
        "hours": rel_delta.hours,
        "minutes": rel_delta.minutes,
        "seconds": rel_delta.seconds,
    }
    return _select_parts(amounts, mode, max_units) + output_suffix


@overload
def human_timedelta(
    td: dt.timedelta,
    *,
    max_units: int | None = 3,
    mode: HumanTimedeltaMode = "full",
) -> str: ...


@overload
def human_timedelta(
    *,
    days: float | None = None,
    hours: float | None = None,
    minutes: float | None = None,
    seconds: float | None = None,
    max_units: int | None = 3,
    mode: HumanTimedeltaMode = "full",
) -> str: ...


def human_timedelta(
    td: dt.timedelta | None = None,
    *,
    days: float | None = None,
    hours: float | None = None,
    minutes: float | None = None,
    seconds: float | None = None,
    max_units: int | None = 2,
    mode: HumanTimedeltaMode = "full",
) -> str:
    """Convert timestamp to human readable words.

    This doesn't support output further than days, e.g. 500 days.

    This function treats "negative" timedeltas the same as positive, e.g. `hours=-2` will print '2 hours'

    Parameters
    ----------
    td
        Timedelta object to convert to a "human" format.
    days
        Days
    hours
        Hours
    minutes
        Minutes
    seconds
        Seconds
    max_units
        Amount of words to allow in the result. Pass ``None`` for full accuracy.
        This truncates the output.
    mode
        Formatting choice for the output. See examples.

    Returns
    -------
    str
        Human-readable description for the timedelta.

    Examples
    --------
    .. code-block:: python

        td = dt.timedelta(hours=2, seconds=66)
        human_timedelta(td, mode="full")  # "2 hours 1 minute 6 seconds"
        human_timedelta(td, mode="short")  # "2 hrs 1 min 6 sec"
        human_timedelta(td, mode="letter")  # "02h01m06s"

    """
    if all(x is None for x in (td, days, hours, minutes, seconds)):
        msg = "At least one argument from `td`, `days`, `hours`, `minutes`, `seconds` is required"
        raise TypeError(msg)
    if td is None:
        td = dt.timedelta(days=days or 0, hours=hours or 0, minutes=minutes or 0, seconds=seconds or 0)
    elif any(x is not None for x in (days, hours, minutes, seconds)):
        msg = "Cannot mix `td` with `days`, `hours`, `minutes`, `seconds` arguments"
        raise TypeError(msg)

    _validate_mode(mode)
    _validate_max_units(max_units)

    total_seconds = abs(td) // dt.timedelta(seconds=1)
    mins, secs = divmod(total_seconds, 60)
    hrs, mins = divmod(mins, 60)
    days_, hrs = divmod(hrs, 24)

    amounts: dict[TimeUnitLiteral, int] = {"days": days_, "hours": hrs, "minutes": mins, "seconds": secs}
    return _select_parts(amounts, mode, max_units)


@copy_doc(format_dt)
def discord(when: dt.datetime, /, style: TimestampStyle | None = None) -> str:
    """Alias for `discord.utils.format_dt`."""
    return format_dt(when, style)
