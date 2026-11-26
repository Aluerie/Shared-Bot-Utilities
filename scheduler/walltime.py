# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Wall time: a time on the clocks of a timezone, as opposed to an absolute moment.

Future events that people set in their local time ("tomorrow at 10:00", "my birthday at midnight") are stored as
the local time plus the IANA timezone, not as UTC. If the timezone's rules change after the event was set
(a country drops DST, moves its offset), the event still happens at 10:00 on the local clocks.
UTC is only derived from the wall time when needed, with the timezone rules known at that moment.

Absolute events ("in 2 hours") are wall times in UTC: their clock never jumps.
"""

import datetime as dt
import zoneinfo
from dataclasses import dataclass
from typing import Self

__all__ = (
    "UTC",
    "WallTime",
    "When",
    "resolve",
    "to_wall_time",
)

UTC = "UTC"
"""Timezone of absolute wall times."""


def resolve(local: dt.datetime, timezone: str) -> dt.datetime:
    """Turn a naive local time in the timezone into an aware UTC moment.

    The rules for the times that the clocks skip or show twice match PostgreSQL's ``timestamp AT TIME ZONE``,
    so the bot shows exactly the moment the database fires the job at:

    * skipped (spring forward, e.g. 02:30 that never happens): the offset from before the transition,
      so 02:30 behaves like 03:30;
    * repeated (fall back, e.g. 02:30 that happens twice): the later of the two moments.

    Parameters
    ----------
    local
        Naive datetime: the time on the clocks of the timezone.
    timezone
        IANA timezone key, e.g. "Europe/Berlin".

    Returns
    -------
    dt.datetime
        The moment as an aware UTC datetime.
    """
    zone = zoneinfo.ZoneInfo(timezone)
    first = local.replace(tzinfo=zone, fold=0)
    second = local.replace(tzinfo=zone, fold=1)
    if first.utcoffset() == second.utcoffset():
        return first.astimezone(dt.UTC)

    # The offsets differ in both a gap and an overlap. In a gap the time doesn't survive a round trip.
    is_gap = first.astimezone(dt.UTC).astimezone(zone).replace(tzinfo=None) != local
    return (first if is_gap else second).astimezone(dt.UTC)


@dataclass(frozen=True, slots=True)
class WallTime:
    """A time on the clocks of a timezone.

    Attributes
    ----------
    local
        Naive datetime: what the clocks show.
    timezone
        IANA timezone key. ``"UTC"`` makes the time absolute.
    """

    local: dt.datetime
    timezone: str = UTC

    def __post_init__(self) -> None:
        if self.local.tzinfo is not None:
            msg = f"WallTime.local must be naive, got {self.local!r}. Use `WallTime.from_aware` for aware datetimes."
            raise ValueError(msg)
        # raises `ZoneInfoNotFoundError` (a `KeyError`) for unknown keys
        zoneinfo.ZoneInfo(self.timezone)

    @classmethod
    def from_aware(cls, moment: dt.datetime, timezone: str = UTC) -> Self:
        """Make a wall time from an aware moment, as it's seen on the clocks of the timezone.

        Parameters
        ----------
        moment
            Aware datetime.
        timezone
            IANA timezone key whose clocks to read. The default, UTC, makes the time absolute.
        """
        if moment.tzinfo is None or moment.utcoffset() is None:
            msg = f"`moment` must be aware, got {moment!r}."
            raise ValueError(msg)
        local = moment.astimezone(zoneinfo.ZoneInfo(timezone)).replace(tzinfo=None, fold=0)
        return cls(local, timezone)

    @property
    def is_absolute(self) -> bool:
        """Whether this is an absolute time (UTC), i.e. "in 2 hours" rather than "at 10:00"."""
        return self.timezone == UTC

    def to_utc(self) -> dt.datetime:
        """Get the moment the clocks of the timezone show this time, as an aware UTC datetime."""
        return resolve(self.local, self.timezone)

    def __add__(self, delta: dt.timedelta) -> Self:
        """Shift the clock time: ``+ timedelta(days=1)`` is the same clock time tomorrow, even across DST."""
        return type(self)(self.local + delta, self.timezone)


type When = dt.datetime | WallTime
"""An aware datetime (an absolute moment) or a wall time."""


def to_wall_time(when: When, timezone: str = UTC) -> WallTime:
    """Normalize `When` into a wall time; aware datetimes are read on the clocks of `timezone`.

    Parameters
    ----------
    when
        Aware datetime or a wall time. Wall times are returned as they are.
    timezone
        IANA timezone key to read aware datetimes in. The default, UTC, keeps them absolute.
    """
    if isinstance(when, WallTime):
        return when
    return WallTime.from_aware(when, timezone)
