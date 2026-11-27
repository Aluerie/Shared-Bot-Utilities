# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Syncing a bot's app commands with Discord only when they changed.

Syncing on every start is simple, but Discord rate-limits it. Instead, the bot's commands are compared with the ones
Discord has registered (one GET request), and synced only if they differ. Discord's copy is the state, so nothing is
stored anywhere: it works the same at home, on the VPS and in a container.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

    import discord
    from discord import app_commands

__all__ = (
    "changed_commands",
    "sync_if_changed",
)

COMPARED_KEYS = frozenset({
    "name",
    "type",
    "description",
    "options",
    "required",
    "choices",
    "value",
    "min_value",
    "max_value",
    "min_length",
    "max_length",
    "autocomplete",
    "channel_types",
    "default_member_permissions",
    "nsfw",
})
"""Fields of a command (and its options and choices) that decide whether Discord has it right.

Discord adds fields of its own (IDs, versions) and fills in defaults (``contexts``, ``integration_types``) that
discord.py leaves out, so comparing everything would see a change on every start.
"""


def _normalized(payload: Any) -> Any:
    """Keep only the compared fields of a command payload, recursively, dropping empty or default ones.

    Two more differences that aren't changes: Discord returns ``default_member_permissions`` as a string while
    discord.py sends a number, and it strips the emoji variation selector (U+FE0F) from texts ("⚔️" comes back "⚔").
    """
    if isinstance(payload, dict):
        return {
            key: str(value) if key == "default_member_permissions" else _normalized(value)
            for key, value in payload.items()
            if key in COMPARED_KEYS and value not in (None, False, "", [])
        }
    if isinstance(payload, list):
        return [_normalized(item) for item in payload]
    if isinstance(payload, str):
        return payload.replace("\N{VARIATION SELECTOR-16}", "")
    return payload


def _signatures(payloads: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Map each command (by type and name) to its normalized payload as JSON, for comparing."""
    return {
        f"{payload.get('type', 1)}:{payload['name']}": json.dumps(_normalized(payload), sort_keys=True)
        for payload in payloads
    }


def changed_commands(local: Iterable[dict[str, Any]], remote: Iterable[dict[str, Any]]) -> list[str]:
    """Name the commands that differ between the bot's tree and what Discord has: new, changed or removed ones.

    Parameters
    ----------
    local
        The bot's command payloads (``command.to_dict(tree)``).
    remote
        The payloads Discord returns for the registered commands.
    """
    ours, theirs = _signatures(local), _signatures(remote)
    names = {key.split(":", 1)[1] for key in ours.keys() ^ theirs.keys()}
    names |= {key.split(":", 1)[1] for key in ours.keys() & theirs.keys() if ours[key] != theirs[key]}
    return sorted(names)


async def sync_if_changed(
    tree: app_commands.CommandTree[Any], *, guild: discord.abc.Snowflake | None = None
) -> list[str]:
    """Sync the global (or one guild's) app commands with Discord, if they changed.

    The bot must be logged in (it needs its application ID).

    Parameters
    ----------
    tree
        The bot's command tree.
    guild
        The guild whose guild-only commands to sync; `None` for the global commands.

    Returns
    -------
    list[str]
        The names of the commands that changed (and got synced); empty if nothing needed syncing.
    """
    client = tree.client
    application_id = client.application_id
    if application_id is None:
        msg = "The bot isn't logged in yet: it needs its application ID to compare the commands."
        raise RuntimeError(msg)

    local = [command.to_dict(tree) for command in tree.get_commands(guild=guild)]
    if guild is None:
        remote = await client.http.get_global_commands(application_id)
    else:
        remote = await client.http.get_guild_commands(application_id, guild.id)

    changed = changed_commands(local, remote)
    if changed:
        await tree.sync(guild=guild)
    return changed
