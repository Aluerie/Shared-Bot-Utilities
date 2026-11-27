# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Tests for ``runtime``."""

import asyncio
import os
import signal
import socket
import sys
import threading
import time
from typing import TYPE_CHECKING

import pytest

from shared import runtime

if TYPE_CHECKING:
    from pathlib import Path

unix_only = pytest.mark.skipif(sys.platform == "win32", reason="Unix sockets and SIGTERM handlers")


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module's state and the environment variables it reads."""
    for name in ("BOT_ENV", "BOT_HEALTH_FILE", "NOTIFY_SOCKET", "WATCHDOG_USEC"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(runtime, "_ready", False)
    monkeypatch.setattr(runtime, "_freeze_thread", None)


def test_is_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not runtime.is_prod()
    monkeypatch.setenv("BOT_ENV", "dev")
    assert not runtime.is_prod()
    monkeypatch.setenv("BOT_ENV", "prod")
    assert runtime.is_prod()


def test_sd_notify_without_socket_does_nothing() -> None:
    runtime.sd_notify("READY=1")  # must not raise


@unix_only
def test_sd_notify_sends_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    address = str(tmp_path / "notify.sock")
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
        server.bind(address)
        monkeypatch.setenv("NOTIFY_SOCKET", address)
        runtime.sd_notify("READY=1")
        assert server.recv(64) == b"READY=1"


def test_notify_ready_touches_the_health_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    health_file = tmp_path / "healthy"
    monkeypatch.setenv("BOT_HEALTH_FILE", str(health_file))
    runtime.notify_ready()
    assert health_file.exists()


async def test_watchdog_loop_touches_the_health_file_only_once_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    health_file = tmp_path / "healthy"
    monkeypatch.setenv("BOT_HEALTH_FILE", str(health_file))
    monkeypatch.setattr(runtime, "TICK_SECONDS", 0.01)
    monkeypatch.setattr(runtime, "_watch_for_freezes", lambda: None)  # no real freeze detector in tests

    task = asyncio.create_task(runtime.watchdog_loop())
    await asyncio.sleep(0.05)
    assert not health_file.exists()

    monkeypatch.setattr(runtime, "_ready", True)
    await asyncio.sleep(0.05)
    task.cancel()
    assert health_file.exists()


def test_freeze_detector_exits_when_the_loop_stops_ticking(monkeypatch: pytest.MonkeyPatch) -> None:
    exits: list[int] = []

    def fake_exit(code: int) -> None:
        exits.append(code)
        raise SystemExit  # ends the detector's thread instead of the test process

    monkeypatch.setattr(runtime.os, "_exit", fake_exit)
    monkeypatch.setattr(runtime.faulthandler, "dump_traceback", lambda **_: None)
    monkeypatch.setattr(runtime, "TICK_SECONDS", 0.01)
    monkeypatch.setattr(runtime, "FREEZE_SECONDS", 0.05)
    monkeypatch.setattr(runtime, "_last_tick", time.monotonic())

    thread = threading.Thread(target=runtime._watch_for_freezes, daemon=True)
    thread.start()
    thread.join(timeout=2)

    assert exits == [runtime.FROZEN_EXIT_CODE]


@unix_only
async def test_sigterm_cancels_main_and_ends_cleanly() -> None:
    cleaned_up = asyncio.Event()

    async def main() -> None:
        try:
            await asyncio.sleep(60)
        finally:
            cleaned_up.set()

    async def send_sigterm() -> None:
        await asyncio.sleep(0.05)
        os.kill(os.getpid(), signal.SIGTERM)

    sender = asyncio.create_task(send_sigterm())
    try:
        await asyncio.wait_for(runtime.run_until_sigterm(main()), timeout=5)  # returns instead of raising
    finally:
        asyncio.get_running_loop().remove_signal_handler(signal.SIGTERM)
    await sender
    assert cleaned_up.is_set()


async def test_main_finishing_on_its_own_just_returns() -> None:
    async def main() -> None:
        await asyncio.sleep(0)

    await runtime.run_until_sigterm(main())
    if sys.platform != "win32":
        asyncio.get_running_loop().remove_signal_handler(signal.SIGTERM)


async def test_other_cancellations_still_propagate() -> None:
    async def main() -> None:
        await asyncio.sleep(60)

    task = asyncio.create_task(runtime.run_until_sigterm(main()))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    if sys.platform != "win32":
        asyncio.get_running_loop().remove_signal_handler(signal.SIGTERM)
