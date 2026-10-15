"""Utilities.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


def ni[T](iterable: Iterable[T]) -> T | None:
    """Get next iter element from an iterable.

    Shortcut for ``next(iter(iterable), None)``, which is a quite common construction within this codebase.
    I'm not sure why I'm annoyed to type it out fully, but I am.
    """
    return next(iter(iterable), None)
