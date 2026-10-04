"""Seven TV Wrapper.

This doesn't cover the whole API in any meaningful way (certainly not good enough for PyPI).
Just a few methods and classes that my bots might be using.

In a way, it's a bit egregious as GraphQL API is not supposed to be used this way.
But I guess it's okay to wrap a few very common operations like this.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from .client import *
from .exceptions import *
from .models import *
