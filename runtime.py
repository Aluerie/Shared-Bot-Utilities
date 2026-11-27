# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""How a bot runs under a supervisor: systemd on the VPS now, Docker later, nothing at home.

* `is_prod` tells prod from a run at home, by the ``BOT_ENV=prod`` that the systemd unit (or compose) sets.
* `notify_ready` reports that the bot is ready: ``READY=1`` to systemd, and the health file for Docker.
* `watchdog_loop` keeps proving the event loop isn't stuck: systemd's watchdog pings, the health file, and a thread
  that ends the process when the loop stops ticking, since Docker only restarts processes that exit.
* `run_until_sigterm` turns SIGTERM (``systemctl stop``, ``docker stop``) into a clean shutdown.
"""

from __future__ import annotations

import asyncio
import faulthandler
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from typing import Any

__all__ = ("is_prod", "notify_ready", "run_until_sigterm", "sd_notify", "watchdog_loop")

# How often the watchdog loop ticks, and how long without a tick counts as frozen. systemd's `WatchdogSec=120`
# catches the same freeze on the VPS; this also works in Docker and dumps the stacks first.
TICK_SECONDS = 10.0
FREEZE_SECONDS = 120.0
# Exit code of a frozen process: EX_SOFTWARE, so it doesn't look like a clean stop.
FROZEN_EXIT_CODE = 70

_ready = False
_last_tick = time.monotonic()
_freeze_thread: threading.Thread | None = None


def is_prod() -> bool:
    """Whether this is the bot running in prod on the VPS, rather than at home.

    The systemd unit (and the compose file later) sets ``BOT_ENV=prod``; nothing else does.
    """
    return os.environ.get("BOT_ENV") == "prod"


def sd_notify(state: str) -> None:
    """Send a state message such as ``READY=1`` or ``WATCHDOG=1`` to systemd.

    Does nothing when the process is not started by a systemd unit with ``Type=notify`` (e.g. local development).
    """
    if sys.platform == "win32":
        return
    address = os.environ.get("NOTIFY_SOCKET", "")
    if not address:
        return
    if address.startswith("@"):  # abstract namespace socket
        address = "\0" + address[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:  # ty: ignore[unresolved-attribute, unused-ignore-comment]
            sock.connect(address)
            sock.sendall(state.encode())
    except OSError:
        logger.exception("Failed to notify systemd with {}", state)


def _touch_health_file() -> None:
    """Update the health file that Docker's ``HEALTHCHECK`` looks at, if ``BOT_HEALTH_FILE`` names one."""
    path = os.environ.get("BOT_HEALTH_FILE", "")
    if not path:
        return
    try:
        Path(path).touch()
    except OSError:
        logger.exception("Failed to touch the health file {}", path)


def notify_ready() -> None:
    """Report that the bot finished starting: ``READY=1`` to systemd, and the first touch of the health file."""
    global _ready  # ruff: ignore[global-statement]
    _ready = True
    sd_notify("READY=1")
    _touch_health_file()


def _watch_for_freezes() -> None:
    """End the process when the event loop hasn't ticked for `FREEZE_SECONDS`, after dumping every thread's stack."""
    while True:
        time.sleep(TICK_SECONDS)
        stuck_for = time.monotonic() - _last_tick
        if stuck_for > FREEZE_SECONDS:
            logger.critical("The event loop has been stuck for {:.0f} s. Dumping the stacks and exiting.", stuck_for)
            faulthandler.dump_traceback(all_threads=True)
            os._exit(FROZEN_EXIT_CODE)


async def watchdog_loop() -> None:
    """Prove every `TICK_SECONDS` that the event loop isn't stuck, until cancelled.

    Each tick resets the freeze detector (a thread started on the first call), pings systemd's watchdog if the unit
    has one (``WatchdogSec=``), and, once the bot is ready, touches the health file for Docker.
    """
    global _last_tick, _freeze_thread  # ruff: ignore[global-statement]
    _last_tick = time.monotonic()
    if _freeze_thread is None:
        _freeze_thread = threading.Thread(target=_watch_for_freezes, name="freeze-detector", daemon=True)
        _freeze_thread.start()
    systemd_watchdog = bool(os.environ.get("WATCHDOG_USEC"))
    while True:
        _last_tick = time.monotonic()
        if systemd_watchdog:
            sd_notify("WATCHDOG=1")
        if _ready:
            _touch_health_file()
        await asyncio.sleep(TICK_SECONDS)


async def run_until_sigterm(main: Coroutine[Any, Any, None]) -> None:
    """Run ``main`` until it finishes or the process gets SIGTERM, which cancels it so it can clean up.

    ``main`` should close what it opened when cancelled (``async with`` does), e.g. the Discord connection and the
    database pool. A SIGTERM ends this normally, so the exit code is 0 and systemd counts it as a clean stop.
    On Windows (at home) there's no SIGTERM handler; Ctrl+C works as before.
    """
    task = asyncio.ensure_future(main)
    stopping = False

    def stop() -> None:
        nonlocal stopping
        if not stopping:
            logger.info("Got SIGTERM, shutting down.")
        stopping = True
        task.cancel()

    if sys.platform != "win32":
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop)
    try:
        await task
    except asyncio.CancelledError:
        if not stopping:
            raise
        logger.info("Shut down cleanly.")
