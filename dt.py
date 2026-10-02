"""
Datetime utilities.

License
-------
* License: MPL-2.0, see LICENSE for more details.
* Copyright: (C) 2020-present @Aluerie.
"""

import datetime


def utcnow() -> datetime.datetime:
    """A helper function to return an aware UTC datetime representing the current time.

    Returns
    -------
    datetime.datetime
        The current aware datetime in UTC.
    """
    return datetime.datetime.now(datetime.UTC)
