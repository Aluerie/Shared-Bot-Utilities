"""Datetime utilities.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

import datetime as dt


def utcnow() -> dt.datetime:
    """Get an aware UTC dt.datetime representing the current time.

    Returns
    -------
    dt.datetime
        The current aware datetime in UTC.
    """
    return dt.datetime.now(dt.UTC)
