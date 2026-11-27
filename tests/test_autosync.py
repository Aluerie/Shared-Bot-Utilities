# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Tests for `shared.concepts.autosync`: telling real command changes from Discord's own differences."""

from typing import Any

from shared.concepts.autosync import changed_commands


def command(name: str = "status", description: str = "📊 Show the bots.", **extra: Any) -> dict[str, Any]:
    return {"name": name, "type": 1, "description": description, "default_member_permissions": 32, **extra}


def from_discord(payload: dict[str, Any]) -> dict[str, Any]:
    """How Discord returns a command: its own fields, permissions as a string, no emoji variation selectors."""
    return {
        **payload,
        "id": "1",
        "application_id": "2",
        "version": "3",
        "contexts": [0, 1, 2],
        "integration_types": [0],
        "default_member_permissions": str(payload["default_member_permissions"]),
        "description": payload["description"].replace("\N{VARIATION SELECTOR-16}", ""),
        "nsfw": False,
    }


def test_the_same_commands_need_no_sync() -> None:
    local = [command(), command("versions", "🏷️ Show the commits.")]  # "🏷️" has a variation selector
    remote = [from_discord(payload) for payload in local]
    assert changed_commands(local, remote) == []


def test_changes_are_found() -> None:
    remote = [from_discord(command()), from_discord(command("old"))]
    local = [command(description="📊 Show the bots, better."), command("new")]
    assert changed_commands(local, remote) == ["new", "old", "status"]


def test_option_changes_are_found() -> None:
    option = {"name": "upcoming", "type": 4, "description": "How many.", "min_value": 0, "max_value": 25}
    remote = [from_discord(command("jobs", options=[option]))]
    local = [command("jobs", options=[{**option, "max_value": 10}])]
    assert changed_commands(local, remote) == ["jobs"]


def test_context_menus_are_compared_by_type_and_name() -> None:
    menu = {"name": "Remind me about this", "type": 3}
    assert changed_commands([menu, command()], [menu, from_discord(command())]) == []
    assert changed_commands([command()], [menu, from_discord(command())]) == ["Remind me about this"]
