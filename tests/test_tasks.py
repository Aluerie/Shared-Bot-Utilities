# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Tests for the ``Loop`` subclass in ``shared.concepts.tasks``."""

from typing import Any

from shared.concepts import tasks


class FakeBot:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def wait_until_ready(self) -> None:
        self.calls.append("ready")


class FakeCog:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.bot = FakeBot(calls)

    @tasks.loop(count=1, wait_for_ready=True)
    async def wait_and_hook(self) -> None:
        self.calls.append("body")

    @wait_and_hook.before_loop
    async def wait_and_hook_before(self) -> None:
        self.calls.append("hook")

    @tasks.loop(count=1, wait_for_ready=True)
    async def wait_only(self) -> None:
        self.calls.append("body")

    @tasks.loop(count=1)
    async def hook_only(self) -> None:
        self.calls.append("body")

    @hook_only.before_loop
    async def hook_only_before(self) -> None:
        self.calls.append("hook")


async def run_to_the_end(task_name: str) -> list[str]:
    """Run the task of a fresh cog until it is done and get what was called, in order."""
    calls: list[str] = []
    task: tasks.Loop[Any] = getattr(FakeCog(calls), task_name)
    task.start()
    running = task.get_task()
    assert running is not None
    await running
    return calls


async def test_wait_for_ready_runs_before_the_hook() -> None:
    """The bot has to be ready before the hook, this combination used to silently drop ``wait_for_ready``."""
    assert await run_to_the_end("wait_and_hook") == ["ready", "hook", "body"]


async def test_wait_for_ready_without_a_hook() -> None:
    assert await run_to_the_end("wait_only") == ["ready", "body"]


async def test_hook_without_wait_for_ready() -> None:
    assert await run_to_the_end("hook_only") == ["hook", "body"]
