"""Time and datetime utilities.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

import datetime as dt
from typing import Literal

from dateutil.relativedelta import relativedelta

from .fmt import human_join, plural


def utcnow() -> dt.datetime:
    """Get an aware UTC dt.datetime representing the current time.

    Returns
    -------
    dt.datetime
        The current aware datetime in UTC.
    """
    return dt.datetime.now(dt.UTC)


def round_to_next_hour(time_dt: dt.datetime) -> dt.datetime:
    """Round to next hour.

    Source
    ------
    * https://stackoverflow.com/a/48108115
    """
    return time_dt.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)


def _fix_datetime(ts: dt.datetime) -> dt.datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.UTC)
    ts = ts.replace(microsecond=0)  # Microsecond free zone
    return ts.astimezone(dt.UTC)  # Make sure everything is UTC


def human_timedelta(
    ts: dt.datetime | dt.timedelta | float,
    *,
    source: dt.datetime | None = None,
    accuracy: int | None = 2,
    mode: Literal["full", "short", "letter"] = "full",
    suffix: bool = False,
    strip: bool = False,
) -> str:
    """Convert `dt.timedelta` to a string of humanly readable words.

    Source
    ------
    * licensed MPL v2 from Rapptz/RoboDanny
        https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/utils/time.py

    Parameters
    ----------
    ts: dt.datetime | dt.timedelta | float
        Represents a "timestamp" object.
        if it is int/float/timedelta then it's assumed to be in the past (as in "dt: int = 5" -> 5 seconds ago)
    source
        Timestamp source to compare against, if `ts` is of type `dt.datetime`. Assumed as now if not given
    accuracy: int = 2
        Amount of words to allow in the result. This is called accuracy because effectively,
        we are cutting down on how accurately the wording represents the time delta.
    mode: Literal["full", "short", "letter"] = "full"
        A formatting choice for the output. See examples.
    suffix
        If to include 'ago' into return string for past times.
    strip
        Whether strip the output from spaces.

    Returns
    -------
    str
        Human-readable description for the time delta.

    Example:
    -------
    ```
    x = datetime.timedelta(seconds=66)
    human_timedelta(x, mode="full")  # "1 minute 6 seconds"
    human_timedelta(x, mode="short")  # "1 min 6 seconds"
    human_timedelta(x, mode="letter")  # "1m6s"
    ```
    """
    now = source or utcnow()

    match ts:
        case dt.datetime():
            pass
        case dt.timedelta():
            ts = now - ts
        case int() | float():
            ts = now - dt.timedelta(seconds=ts)

    now = _fix_datetime(now)
    ts = _fix_datetime(ts)

    # This implementation uses relativedelta instead of the much more obvious
    # divmod approach with seconds because the seconds approach is not entirely
    # accurate once you go over 1 week in terms of accuracy since you have to
    # hardcode a month as 30 or 31 days.
    # A query like "11 months" can be interpreted as "!1 months and 6 days"
    if ts > now:
        delta = relativedelta(ts, now)
        output_suffix = ""
    else:
        delta = relativedelta(now, ts)
        output_suffix = " ago" if suffix else ""

    attrs = [
        ("year", "year", "y"),
        ("month", "month", "mo"),
        ("day", "day", "d"),
        ("hour", "hr", "h"),
        ("minute", "min", "m"),
        ("second", "sec", "s"),
    ]

    output = []
    for index, (full_attr, short_attr, letter_attr) in enumerate(attrs):
        elem = getattr(delta, full_attr + "s")
        if not elem:
            continue

        if full_attr == "day":
            weeks = delta.weeks
            if weeks:
                elem -= weeks * 7
                if mode == "full":
                    output.append(format(plural(weeks), "week"))
                elif mode == "short":
                    output.append(f"{weeks} wk")
                else:
                    output.append(f"{weeks}w")

        if elem <= 0:
            continue

        if mode == "full":
            output.append(format(plural(elem), full_attr))
        elif mode == "short":
            to_append = format(plural(elem), short_attr) if index < 3 else f"{elem} {short_attr}"
            output.append(to_append)
        else:
            output.append(f"{elem}{letter_attr}")

    if accuracy is not None:
        output = output[:accuracy]

    if len(output) == 0:
        return "now"
    if mode == "full":
        return human_join(output, final="and") + output_suffix
    sep = "" if strip else " "
    return sep.join(output) + output_suffix


def dm_human_timedelta(
    ts: dt.datetime | dt.timedelta | float,
    *,
    source: dt.datetime | None = None,
    accuracy: int = 2,
    mode: Literal["full", "short", "letter"] = "full",
) -> str:
    """Convert timestamp to human readable words.

    Parameters are the same as in `human_timedelta` so I will be lazy.
    Just know that the difference between this function and `human_timedelta` is that
    the former uses `relativedelta` approach instead of much more obvious `divmod` approach.
    The problem is that `divmod` approach becomes not entirely accurate once we go over 1 week since
    we have to hardcode month as 30 or 31 days, etc. A query like "11 months" can be interpreted as "11 months and 6 days".

    But I guess, this function is a bit more efficient, if we care about it.
    So you can use this function if we don't need to use "weeks", "months", "years" in the output.

    Source
    ------
    * `?tag format timedelta` in Discord.py guild.
    """
    if isinstance(ts, dt.timedelta):
        total_seconds = int(ts.total_seconds())
    elif isinstance(ts, (int, float)):
        total_seconds = int(ts)
    elif isinstance(ts, dt.datetime):
        now = source or utcnow()
        now = _fix_datetime(now)
        ts = _fix_datetime(ts)
        total_seconds = int((now - ts).total_seconds())
    else:
        msg = "Argument `ts` should be one of the following types: dt.datetime, dt.timedelta, int or float."
        raise TypeError(msg)

    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    def get_time_units(*names: str) -> dict[str, int]:
        return dict(zip(names, (days, hours, minutes, seconds), strict=True))

    match mode:
        case "full":
            # 1 minute 6 seconds
            time_units = get_time_units("day", "hour", "minute", "second")
            output = [format(plural(number), word) for word, number in time_units.items() if number]
            return " ".join(output[:accuracy])
        case "short":
            # 1 min 30 sec
            time_units = get_time_units(f"{plural(days):day!}", "hr", "min", "sec")
            output = [f"{number} {word}" for word, number in time_units.items() if number]
            return " ".join(output[:accuracy])
        case "letter":
            # 1m30s
            time_units = get_time_units("d", "h", "m", "s")
            output = [f"{number:02d}{letter}" for letter, number in time_units.items() if number]
            return "".join(output[:accuracy]).removeprefix("0")  # remove leading zero if it managed to sneak in
        case _:
            msg = "Incorrect mode passed"
            raise RuntimeError(msg)


# TODO: look at https://discord.com/channels/336642139381301249/559455534965850142/1516505091207860351
