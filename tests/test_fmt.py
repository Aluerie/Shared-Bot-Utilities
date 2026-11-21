# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Tests for ``shared.fmt``."""

import pytest

from shared import fmt


def test_codeblock() -> None:
    assert fmt.codeblock("print(1)") == "```py\nprint(1)\n```"
    assert fmt.codeblock("text", "") == "```\ntext\n```"


@pytest.mark.parametrize("amount", range(1, 10))
def test_codeblock_cannot_be_closed_early(amount: int) -> None:
    inner = fmt.codeblock("a" + "`" * amount + "b", "")[3:-3]
    assert "```" not in inner


def test_escape_backticks_keeps_text_and_is_idempotent() -> None:
    text = "x ``` y ````` z"
    escaped = fmt.escape_backticks(text)
    assert escaped.replace("\u200b", "") == text
    assert fmt.escape_backticks(escaped) == escaped


def test_pformat_mapping() -> None:
    assert fmt.pformat_mapping({}) == fmt.codeblock("No arguments")
    assert fmt.pformat_mapping({"a": 1, "long_name": "x"}) == fmt.codeblock("a         = 1\nlong_name = 'x'")


def test_pformat_mapping_respects_limit() -> None:
    result = fmt.pformat_mapping({"key": "v" * 5000}, limit=fmt.EMBED_FIELD_VALUE_LIMIT)
    assert len(result) <= fmt.EMBED_FIELD_VALUE_LIMIT
    assert result.endswith("…\n```")


def test_pformat_args() -> None:
    assert fmt.pformat_args(1, "two") == fmt.codeblock("arg_0 = 1\narg_1 = 'two'")


@pytest.mark.parametrize(
    ("number", "expected"),
    [(0, "0th"), (1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"), (12, "12th"), (13, "13th"),
     (21, "21st"), (102, "102nd"), (111, "111th"), ("3", "3rd"), (-1, "-1st")],
)  # fmt: skip
def test_ordinal(number: int | str, expected: str) -> None:
    assert fmt.ordinal(number) == expected


@pytest.mark.parametrize(
    ("number", "spec", "expected"),
    [
        (1, "reminder", "1 reminder"),
        (3, "reminder", "3 reminders"),
        (0, "reminder", "0 reminders"),
        (1, "child|children", "1 child"),
        (2, "child|children", "2 children"),
        (3, "reminder!", "reminders"),
        (1, "reminder!", "reminder"),
    ],
)
def test_plural(number: int, spec: str, expected: str) -> None:
    assert format(fmt.plural(number), spec) == expected


@pytest.mark.parametrize(
    ("seq", "expected"),
    [
        ([], ""),
        (["a"], "a"),
        (["a", "b"], "a or b"),
        (["a", "b", "c"], "a, b or c"),
    ],
)
def test_human_join(seq: list[str], expected: str) -> None:
    assert fmt.human_join(seq) == expected


def test_human_join_custom_final() -> None:
    assert (
        fmt.human_join(["Conan Doyle", "Nabokov", "Fitzgerald"], final="and") == "Conan Doyle, Nabokov and Fitzgerald"
    )


def test_bullet_list() -> None:
    assert fmt.bullet_list(["a", "b"]) == "* a\n* b"


@pytest.mark.parametrize(
    ("text", "limit", "expected"),
    [
        ("hello", 10, "hello"),
        ("hello", 5, "hello"),
        ("hello world", 5, "hell…"),
        ("hello", 1, "…"),
        ("hello", 0, ""),
    ],
)
def test_shorten(text: str, limit: int, expected: str) -> None:
    assert fmt.shorten(text, limit) == expected
    assert len(fmt.shorten(text, limit)) <= max(limit, 0)
