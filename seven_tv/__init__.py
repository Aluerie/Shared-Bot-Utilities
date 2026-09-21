"""
Seven TV Wrapper.

This doesn't cover the whole API in any meaningful ways.
Certainly not for PyPI (Python Package Index).
Just a few methods and classes that this bot will be using.

In a way, it's a bit egregious as GraphQL API is not supposed to be used this way.
But I guess it's okay to wrap it like this for some very common operations.

License
-------
* License: MPL-2.0, see LICENSE for more details.
* Copyright: (C) 2020-present @Aluerie.
"""

from .client import *
from .exceptions import *
from .models import *
