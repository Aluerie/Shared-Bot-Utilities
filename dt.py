"""
Datetime utilities.

License
-------
* This Source Code Form is subject to the terms of the [Mozilla Public License v2.0](<http://mozilla.org/MPL/2.0/>).
* Copyright (C) 2020-present [@Aluerie](<https://github.com/Aluerie>).
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
