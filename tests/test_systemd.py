# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Tests for ``systemd``."""

import socket
import sys
from typing import TYPE_CHECKING

import pytest

from shared import systemd

if TYPE_CHECKING:
    from pathlib import Path


def test_is_systemd_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    assert not systemd.is_systemd_service()
    monkeypatch.setenv("INVOCATION_ID", "0123456789abcdef")
    assert systemd.is_systemd_service()


def test_sd_notify_without_socket_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    systemd.sd_notify("READY=1")  # must not raise


def test_sd_notify_sends_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("systemd notify sockets are Unix sockets")
    address = str(tmp_path / "notify.sock")
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
        server.bind(address)
        monkeypatch.setenv("NOTIFY_SOCKET", address)
        systemd.sd_notify("READY=1")
        assert server.recv(64) == b"READY=1"


async def test_watchdog_loop_returns_without_watchdog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WATCHDOG_USEC", raising=False)
    await systemd.watchdog_loop()  # returns right away instead of looping forever
