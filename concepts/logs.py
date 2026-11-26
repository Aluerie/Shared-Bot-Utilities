# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Logging Setup.

All our own code logs with `loguru`. Libraries (discord.py, twitchio, steam.py, aiohttp, ...) still use the
standard `logging` module, so `InterceptHandler` re-routes their records into loguru, and everything ends up
in the same sinks (console and Discord webhook).
In production the console output goes to the systemd journal (or a container's log), so there is no log file.
"""

from __future__ import annotations

import logging
import platform
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Final, override

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Generator

    from loguru import Logger, Record

__all__ = (
    "InterceptHandler",
    "prefixed_logger",
    "setup_logging",
)

CONSOLE_FORMAT: Final = (
    "<white><bold>{time:HH:mm:ss DD/MM!UTC}</bold></white> {level.icon} <level>{level: <8.8}</level> "
    "<magenta>{name: <30}</magenta> <light-green>{line: <4}</light-green> <cyan>{function: <35}</cyan> {message}"
)
# Level name -> (colour, icon). Loguru's built-in levels, from the most verbose:
# TRACE (5), DEBUG (10), INFO (20), SUCCESS (25), WARNING (30), ERROR (40), CRITICAL (50).
# Icons are shown in the console and the Discord webhook. They are all double-width emojis
# without the `U+FE0F` variation selector (unlike the usual info/warning sign emojis),
# so the columns stay aligned in any terminal.
LEVELS: Final[dict[str, tuple[str, str]]] = {
    "TRACE": ("<dim>", "🔍"),
    "DEBUG": ("<BLACK><bold>", "🐛"),
    "INFO": ("<blue><bold>", "💬"),
    "SUCCESS": ("<green><bold>", "✅"),
    "WARNING": ("<yellow><bold>", "🔶"),
    "ERROR": ("<red>", "❌"),
    "CRITICAL": ("<RED>", "💥"),
}


class InterceptHandler(logging.Handler):
    """Standard `logging` handler that forwards records into loguru.

    Libraries keep logging with `logging.getLogger(__name__)`; this handler is attached to the root logger,
    so their records get the same formatting and sinks as ours.
    """

    @override
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        def patch(loguru_record: Record) -> None:
            # Point at the library's code instead of this handler.
            loguru_record.update(name=record.name, function=record.funcName, line=record.lineno)

        exc_info = record.exc_info
        exception = exc_info if isinstance(exc_info, tuple) and exc_info[0] is not None else None
        logger.patch(patch).opt(exception=exception).log(level, record.getMessage())


def prefixed_logger(prefix: str) -> Logger:
    """Get a logger that puts `prefix` in front of every message.

    I like logs from the same module having the same emoji as some sort of identifier.

    Examples
    --------
    ```py
    log = prefixed_logger("🍋")
    log.info("hello {}", "world")  # 🍋 hello world
    ```
    """
    return logger.patch(lambda record: record.update(message=f"{prefix} {record['message']}"))


@contextmanager
def setup_logging(
    *,
    starting_up_art: str,
    level: int | str = logging.INFO,
) -> Generator[None, Any, Any]:
    """Set up logging.

    Parameters
    ----------
    starting_up_art
        Text that is logged on start-up, so restarts are noticeable in the logs.
    level
        Minimum level for the console sink; libraries' standard `logging` records below it
        are dropped too. Debug logs of the libraries show up when it is ``DEBUG``.
        Loguru-only level names such as ``"TRACE"`` or ``"SUCCESS"`` work too.
    """
    logger.remove()  # the default `stderr` sink
    for name, (colour, icon) in LEVELS.items():
        logger.level(name, color=colour, icon=icon)

    root = logging.getLogger()
    intercept_handler = InterceptHandler()
    root.addHandler(intercept_handler)
    # standard `logging` doesn't know loguru-only names like "TRACE"/"SUCCESS", so give it the number
    root.setLevel(logger.level(level).no if isinstance(level, str) else level)

    try:
        # `diagnose=False`: variable values in tracebacks could leak tokens/secrets into the logs.
        logger.add(sys.stderr, level=level, format=CONSOLE_FORMAT, backtrace=True, diagnose=False)

        if platform.system() == "Linux":
            # so start-ups in logs are way more noticeable
            logger.info(starting_up_art)

        yield
    finally:
        # __exit__
        logger.remove()
        root.removeHandler(intercept_handler)
