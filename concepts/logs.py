"""Logging Setup.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

import logging
import platform
import time
import traceback
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, override

import discord

if TYPE_CHECKING:
    from collections.abc import Generator

__all__ = ("setup_logging",)

logging.Formatter.converter = time.gmtime


@contextmanager
def setup_logging(
    *,
    starting_up_art: str,
    filename: str,
) -> Generator[None, Any, Any]:
    """Set up logging."""
    log = logging.getLogger()
    log.setLevel(logging.INFO)

    try:
        # Stream Handler
        handler = logging.StreamHandler()
        handler.setFormatter(fmt=get_logging_formatter(handler))
        log.addHandler(handler)

        # ensure logs folder
        Path(".temp/").mkdir(parents=True, exist_ok=True)
        # File Handler
        file_handler = RotatingFileHandler(
            filename=f".temp/{filename}",
            encoding="utf-8",
            mode="w",
            maxBytes=7 * 1024 * 1024,  # MiB
            backupCount=2,  # Rotate through 2 files
        )
        file_handler.setFormatter(fmt=get_logging_formatter(file_handler))
        log.addHandler(file_handler)

        if platform.system() == "Linux":
            # so start-ups in logs are way more noticeable
            log.info(starting_up_art)

        yield
    finally:
        # __exit__
        handlers = log.handlers[:]
        for h in handlers:
            h.close()
            log.removeHandler(h)


class MyColourFormatter(logging.Formatter):
    r"""My colour formatter.

    Sources
    -------
    * fully copy-pasted from `discord.utils._ColourFormatter` class and changed a few things.

    ANSI Refresher
    --------------
    It starts off with a format like '\x1b[XXXm' where 'XXX' is a semicolon separated list of commands
    The important ones here relate to colour.
    * 30-37 are black, red, green, yellow, blue, magenta, cyan and white in that order
    * 40-47 are the same except for the background
    * 90-97 are the same but "bright" foreground
    * 100-107 are the same as the bright ones but for the background.
    * 1 means bold, 2 means dim, 0 means reset, and 4 means underline.
    """

    # ANSI codes are a bit weird to decipher if you're unfamiliar with them, so here's a refresher

    LEVEL_COLORS = (
        (logging.DEBUG, "\x1b[40;1m"),
        (logging.INFO, "\x1b[34;1m"),
        (logging.WARNING, "\x1b[33;1m"),
        (logging.ERROR, "\x1b[31m"),
        (logging.CRITICAL, "\x1b[41m"),
    )

    FORMATS: ClassVar[dict[int, logging.Formatter]] = {
        level: logging.Formatter(
            fmt=(
                f"\x1b[37;1m%(asctime)s\x1b[0m {color}%(levelname)-8.8s\x1b[0m \x1b[35m%(name)-30s\x1b[0m "
                "\x1b[92m%(lineno)-4d\x1b[0m \x1b[36m%(funcName)-35s\x1b[0m %(message)s"
            ),
            datefmt="%H:%M:%S %d/%m",
        )
        for level, color in LEVEL_COLORS
    }

    @override
    def format(self, record: logging.LogRecord) -> str:
        formatter = self.FORMATS.get(record.levelno)
        if formatter is None:
            formatter = self.FORMATS[logging.DEBUG]

        if record.exc_info:
            # ORIGINAL discord.py:
            # Override the traceback to always print in red
            # text = formatter.formatException(record.exc_info)
            # record.exc_text = f"\x1b[31m{text}\x1b[0m"
            # ------------------------------------------
            # MINE: extra colorization introduced with Python 3.13
            # `colorize=True` is not documented hence 'ignore[no-matching-overload]',
            # but I'm not sure how I'm supposed to do it otherwise;
            # setting `os.environ["FORCE_COLOR"] = 1` doesn't work for `traceback` methods.
            record.exc_text = "".join(
                traceback.format_exception(
                    record.exc_info[0], value=record.exc_info[1], tb=record.exc_info[2], colorize=True
                )  # ty: ignore[no-matching-overload]
            )

        output = formatter.format(record)

        # Remove the cache layer
        record.exc_text = None
        return output


def get_logging_formatter(handler: logging.Handler) -> logging.Formatter:
    return (
        MyColourFormatter()
        if (
            isinstance(handler, logging.StreamHandler)
            and discord.utils.stream_supports_colour(handler.stream)
            and not isinstance(handler, RotatingFileHandler)
        )
        else logging.Formatter(
            fmt="%(asctime)s %(levelname)-8.8s %(name)-30s %(lineno)-4d %(funcName)-35s %(message)s",
            datefmt="%H:%M:%S %d/%m",
        )
    )


class PrefixLoggerAdapter(logging.LoggerAdapter[Any]):
    def __init__(self, logger: logging.Logger, prefix: str) -> None:
        super().__init__(logger)
        self.prefix = prefix

    @override
    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        return f"{self.prefix} {msg}", kwargs
