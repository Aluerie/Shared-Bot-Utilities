# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Tests for the small modules: ``ut``, ``gh``, ``globs`` and ``concepts.logs``."""

from typing import TYPE_CHECKING

from loguru import logger

from shared import gh, globs, ut
from shared.concepts import prefixed_logger

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_ni() -> None:
    assert ut.ni([1, 2]) == 1
    assert ut.ni([]) is None
    assert ut.ni(x for x in "ab") == "a"


def test_missing_sentinel() -> None:
    assert not ut.MISSING
    assert ut.MISSING != ut.MISSING
    assert repr(ut.MISSING) == "..."


async def test_measure_time_logs(caplog: pytest.LogCaptureFixture) -> None:
    with ut.measure_time("sync block", logger=logger) as timer:
        pass
    async with ut.measure_time("async block", logger=logger):
        pass
    assert timer.end >= 0
    assert "sync block PT" in caplog.text
    assert "async block PT" in caplog.text


def test_emojified_title() -> None:
    def title(short_title: str) -> str:
        info = gh.CommitInfo(
            repo=None,  # ty: ignore[invalid-argument-type]
            id=None,  # ty: ignore[invalid-argument-type]
            short_title=short_title,
            short_sha2="abc1234",
            utc_dt=None,  # ty: ignore[invalid-argument-type]
            tz=None,  # ty: ignore[invalid-argument-type]
        )
        return info.emojified_title

    assert title(":bug: Fix it") == "🐛 Fix it"
    assert title(":not_a_gitmoji: Hm") == ":not_a_gitmoji: Hm"
    assert title("No emoji :bug:") == "No emoji :bug:"  # only at the start


def test_count_lines(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("1\n2\n3\n")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "b.py").write_text("1\n")
    (tmp_path / "notes.txt").write_text("not python\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "c.py").write_text("excluded\n")
    assert gh.count_lines(tmp_path) == 4


def test_globs_constants() -> None:
    assert len(globs.DIGITS) == 10
    assert globs.Color.BLACK == 0x000000
    assert globs.Color.WHITE == 0xFFFFFF
    assert all(0 <= color <= 0xFFFFFF for color in globs.Color)


def test_prefixed_logger(caplog: pytest.LogCaptureFixture) -> None:
    prefixed_logger("🍋").info("hello {}", "world")
    assert caplog.messages == ["🍋 hello world"]
