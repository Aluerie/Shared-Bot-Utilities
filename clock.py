"""Time and datetime utilities.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

import datetime
from typing import Literal, assert_never, get_args

from dateutil.relativedelta import relativedelta

from .fmt import plural

#############################################################################################################################
# Get time
#############################################################################################################################


def utcnow() -> datetime.datetime:
    """Get an aware UTC datetime.datetime representing the current time.

    Returns
    -------
    datetime.datetime
        The current aware datetime in UTC.
    """
    return datetime.datetime.now(datetime.UTC)


def round_to_next_hour(dt: datetime.datetime) -> datetime.datetime:
    """Round to next hour.

    This always advances. (e.g. 12:00:00 becomes 13:00:00)

    Source
    ------
    * https://stackoverflow.com/a/48108115

    Parameters
    ----------
    dt
        The datetime to round up.

    Returns
    -------
    datetime.datetime
        The start of the next hour.
    """
    return dt.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)


#############################################################################################################################
# Human Timedelta
#############################################################################################################################


HumanTimedeltaMode = Literal["full", "short", "letter"]


_BAD_DT_TYPE_MSG = (
    "Argument `dt` should be one of the following types: datetime.datetime, datetime.timedelta, int or float. "
    "Instead got {0}"
)


def _validate_mode(mode: str) -> None:
    literal_args = get_args(HumanTimedeltaMode)
    if mode not in literal_args:
        msg = f"`mode` should be one of {literal_args}, got {mode!r}."
        raise ValueError(msg)


def _validate_accuracy(accuracy: int | None) -> None:
    if accuracy is not None and accuracy < 1:
        msg = "`accuracy` should be at least 1 (or None for no limit)."
        raise ValueError(msg)


def _fix_datetime(dt: datetime.datetime) -> datetime.datetime:
    """'Fix' datetime.datetime object.

    * makes it timezone-aware (naive datetimes are assumed to be UTC);
    * removes microseconds;
    * converts to UTC timezone;
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)
    dt = dt.replace(microsecond=0)
    return dt.astimezone(datetime.UTC)


def human_timedelta(
    dt: datetime.datetime | datetime.timedelta | float,
    *,
    source: datetime.datetime | None = None,
    accuracy: int | None = 2,
    mode: HumanTimedeltaMode = "full",
) -> str:
    """Convert ``dt`` to a string of humanly readable words.

    Source
    ------
    * licensed MPL v2 from Rapptz/RoboDanny
        https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/utils/time.py

    Parameters
    ----------
    dt
        Represents a "timestamp" object.
        if it is int/float/timedelta then it's assumed to be in the past (as in "dt: int = 5" -> 5 seconds ago)
    source
        Timestamp source to compare against, if ``dt`` is of type ``datetime.datetime.`` Assumed as now if not given.
    accuracy
        Amount of words to allow in the result. This is called accuracy because effectively,
        we are cutting down on how accurately the wording represents the time delta.
        Pass ``None`` for full accuracy.
    mode
        Formatting choice for the output. See examples.

    Returns
    -------
    str
        Human-readable description for the time delta.

    Examples
    --------
    .. code-block::

        x = datetime.timedelta(seconds=66)
        human_timedelta(x, mode="full")  # "1 minute 6 seconds"
        human_timedelta(x, mode="short")  # "1 min 6 sec"
        human_timedelta(x, mode="letter")  # "01m06s"

    """
    _validate_mode(mode)
    _validate_accuracy(accuracy)

    now = _fix_datetime(source or utcnow())

    match dt:
        case bool():
            # bool is a subclass of int, but passing it is wrong
            raise TypeError(_BAD_DT_TYPE_MSG)
        case datetime.datetime():
            pass
        case datetime.timedelta():
            dt = now - dt
        case int() | float():
            dt = now - datetime.timedelta(seconds=dt)
        case _:
            msg = _BAD_DT_TYPE_MSG.format(type(dt))
            raise TypeError(msg)

    dt = _fix_datetime(dt)

    delta = relativedelta(dt, now) if dt > now else relativedelta(now, dt)

    attrs = [
        ("year", "year", "y", True),
        ("month", "month", "mo", True),
        ("day", "day", "d", True),
        ("hour", "hr", "h", False),
        ("minute", "min", "m", False),
        ("second", "sec", "s", False),
    ]

    output = []
    for full, short, letter, use_plural_in_short_mode in attrs:
        elem: int = getattr(delta, full + "s")  # delta.years, delta.months, delta.days, ...
        if not elem:
            continue

        if mode == "full":
            output.append(format(plural(elem), full))
        elif mode == "short":
            to_append = format(plural(elem), short) if use_plural_in_short_mode else f"{elem} {short}"
            output.append(to_append)
        elif mode == "letter":
            output.append(f"{elem:02d}{letter}")
        else:
            assert_never(mode)

    if accuracy is not None:
        output = output[:accuracy]

    if not output:
        return "now"
    sep = "" if mode == "letter" else " "
    return sep.join(output)


def dm_human_timedelta(
    dt: datetime.datetime | datetime.timedelta | float,
    *,
    source: datetime.datetime | None = None,
    accuracy: int | None = 2,
    mode: HumanTimedeltaMode = "full",
) -> str:
    """Convert timestamp to human readable words.

    Just know that the difference between this function and `human_timedelta` is that
    the latter uses `relativedelta` approach instead of much more obvious `divmod` approach.
    The problem is that `divmod` approach becomes not entirely accurate once we go over 1 week since
    we have to hardcode month as 30 or 31 days, etc. A query like "11 months" can be interpreted as "11 months and 6 days".

    But I guess, this function is a bit more efficient, if we care about it.
    We should use this function if we don't need to use "weeks", "months", "years" in the output.

    Source
    ------
    * `?tag format timedelta` in Discord.py guild.

    Parameters
    ----------
    dt
        Represents a "timestamp" object.
        if it is int/float/timedelta then it's assumed to be in the past (as in "dt: int = 5" -> 5 seconds ago)
    source
        Timestamp source to compare against, if ``dt`` is of type ``datetime.datetime.`` Assumed as now if not given.
    accuracy
        Amount of words to allow in the result. This is called accuracy because effectively,
        we are cutting down on how accurately the wording represents the time delta.
        Pass ``None`` for full accuracy.
    mode
        Formatting choice for the output. See examples.

    """
    _validate_mode(mode)
    _validate_accuracy(accuracy)

    match dt:
        case bool():
            raise TypeError(_BAD_DT_TYPE_MSG)
        case datetime.datetime():
            now = _fix_datetime(source or utcnow())
            total_seconds = (now - _fix_datetime(dt)).total_seconds()
        case datetime.timedelta():
            total_seconds = dt.total_seconds()
        case int() | float():
            total_seconds = dt
        case _:
            raise TypeError(_BAD_DT_TYPE_MSG)

    total_seconds = abs(int(total_seconds))
    if total_seconds == 0:
        return "now"

    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    def get_time_units(*names: str) -> dict[str, int]:
        return dict(zip(names, (days, hours, minutes, seconds), strict=True))

    match mode:
        case "full":
            # 1 minute 30 seconds
            time_units = get_time_units("day", "hour", "minute", "second")
            output = [format(plural(number), word) for word, number in time_units.items() if number]
            sep = " "
        case "short":
            # 1 min 30 sec
            time_units = get_time_units("day" if days == 1 else "days", "hr", "min", "sec")
            output = [f"{number} {word}" for word, number in time_units.items() if number]
            sep = " "
        case "letter":
            # 01m30s
            time_units = get_time_units("d", "h", "m", "s")
            output = [f"{number:02d}{letter}" for letter, number in time_units.items() if number]
            sep = ""
        case _:
            assert_never(mode)

    if accuracy is not None:
        output = output[:accuracy]
    return sep.join(output)
