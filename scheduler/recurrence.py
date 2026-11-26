# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Repeat rules of jobs: RFC 5545 ``RRULE`` strings evaluated on the wall clock.

A rule like ``FREQ=DAILY`` on a job at 09:00 Europe/Berlin keeps firing at 09:00 on Berlin's clocks,
across DST changes, because the occurrences are computed on naive local times.
"""

import datetime as dt
import itertools

lazy from dateutil import rrule as _rrule

__all__ = (
    "InvalidRuleError",
    "min_gap",
    "next_occurrence",
    "validate_rule",
)


class InvalidRuleError(ValueError):
    """The repeat rule can't be used for a job."""


def _parse(rule: str, start: dt.datetime) -> _rrule.rrule:
    try:
        parsed = _rrule.rrulestr(rule, dtstart=start, forceset=False)
    except (ValueError, TypeError) as exc:
        msg = f"Invalid repeat rule {rule!r}: {exc}"
        raise InvalidRuleError(msg) from None
    if not isinstance(parsed, _rrule.rrule):
        msg = f"Repeat rule {rule!r} must be a single RRULE."
        raise InvalidRuleError(msg)
    return parsed


def validate_rule(rule: str, start: dt.datetime) -> None:
    """Check that the rule can repeat a job that starts at `start`.

    ``COUNT`` isn't supported: the job only remembers its next occurrence, so it can't count the past ones.
    Use ``UNTIL`` instead.

    Parameters
    ----------
    rule
        RRULE string without the ``RRULE:`` prefix, e.g. ``FREQ=WEEKLY;BYDAY=MO,FR``.
    start
        Naive local time of the job's first occurrence.

    Raises
    ------
    InvalidRuleError
        If the rule can't be parsed, uses ``COUNT`` or never fires after `start`.
    """
    parsed = _parse(rule, start)
    if "COUNT=" in rule.upper():
        msg = "Repeat rules can't use COUNT, use UNTIL instead."
        raise InvalidRuleError(msg)
    if parsed.after(start) is None:
        msg = f"Repeat rule {rule!r} never fires after {start:%Y-%m-%d %H:%M}."
        raise InvalidRuleError(msg)


def next_occurrence(rule: str, *, current: dt.datetime, after: dt.datetime) -> dt.datetime | None:
    """Get the first occurrence of the rule that is later than both `current` and `after`.

    Taking the later of the two skips the occurrences missed while the bot was down: they collapse into one run.

    Parameters
    ----------
    rule
        RRULE string.
    current
        Naive local time of the occurrence that just ran; the rule's ``DTSTART``.
    after
        Naive local time to skip past, usually "now" on the job's clocks.

    Returns
    -------
    dt.datetime | None
        Naive local time of the next occurrence, or `None` if the rule is over (``UNTIL`` has passed).
    """
    return _parse(rule, current).after(max(current, after))


def min_gap(rule: str, start: dt.datetime, *, sample: int = 50) -> dt.timedelta:
    """Get the shortest time between two consecutive occurrences among the first ones.

    Useful to reject rules that would fire too often (e.g. ``FREQ=MINUTELY``).

    Parameters
    ----------
    rule
        RRULE string.
    start
        Naive local time of the first occurrence.
    sample
        How many occurrences to look at.

    Returns
    -------
    dt.timedelta
        The shortest gap, or `timedelta.max` if the rule fires once at most.
    """
    occurrences: list[dt.datetime] = []
    for occurrence in _parse(rule, start):
        occurrences.append(occurrence)
        if len(occurrences) >= sample:
            break
    return min((b - a for a, b in itertools.pairwise(occurrences)), default=dt.timedelta.max)
