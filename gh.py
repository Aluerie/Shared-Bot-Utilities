# Copyright (C) 2020-present, Irene Adler 💜 (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Git, GitHub and some file/code counting Utilities."""

from __future__ import annotations

import datetime as dt
import itertools
import re
from dataclasses import dataclass
from pathlib import Path

import pygit2
from pygit2.enums import SortMode

__all__ = (
    "count_lines",
    "emojify",
    "get_last_commit",
    "get_latest_commits",
)


GITMOJI_MAPPING = {
    # I freaking love https://gitmoji.dev/specification commit format
    # Even though, it's quite silly.
    # This mapping was made by doing `{g["code"]: g["emoji"] for g in GITMOJIS["gitmojis"]}` where
    # GITEMOJIS is from
    # https://github.com/carloscuesta/gitmoji/blob/master/packages/gitmojis/src/gitmojis.json
    # Last updated: 29/Sep/26
    ":art:": "🎨",
    ":zap:": "⚡️",
    ":fire:": "🔥",
    ":bug:": "🐛",
    ":ambulance:": "🚑️",
    ":sparkles:": "✨",
    ":memo:": "📝",
    ":rocket:": "🚀",
    ":lipstick:": "💄",
    ":tada:": "🎉",
    ":white_check_mark:": "✅",
    ":lock:": "🔒️",
    ":closed_lock_with_key:": "🔐",
    ":bookmark:": "🔖",
    ":rotating_light:": "🚨",
    ":construction:": "🚧",
    ":green_heart:": "💚",
    ":arrow_down:": "⬇️",
    ":arrow_up:": "⬆️",
    ":pushpin:": "📌",
    ":construction_worker:": "👷",
    ":chart_with_upwards_trend:": "📈",
    ":recycle:": "♻️",
    ":heavy_plus_sign:": "➕",
    ":heavy_minus_sign:": "➖",
    ":wrench:": "🔧",
    ":hammer:": "🔨",
    ":globe_with_meridians:": "🌐",
    ":pencil2:": "✏️",
    ":poop:": "💩",
    ":rewind:": "⏪️",
    ":twisted_rightwards_arrows:": "🔀",
    ":package:": "📦️",
    ":alien:": "👽️",
    ":truck:": "🚚",
    ":page_facing_up:": "📄",
    ":boom:": "💥",
    ":bento:": "🍱",
    ":wheelchair:": "♿️",
    ":bulb:": "💡",
    ":beers:": "🍻",
    ":speech_balloon:": "💬",
    ":card_file_box:": "🗃️",
    ":loud_sound:": "🔊",
    ":mute:": "🔇",
    ":busts_in_silhouette:": "👥",
    ":children_crossing:": "🚸",
    ":building_construction:": "🏗️",
    ":iphone:": "📱",
    ":clown_face:": "🤡",
    ":egg:": "🥚",
    ":see_no_evil:": "🙈",
    ":camera_flash:": "📸",
    ":alembic:": "⚗️",
    ":mag:": "🔍️",
    ":label:": "🏷️",
    ":seedling:": "🌱",
    ":triangular_flag_on_post:": "🚩",
    ":goal_net:": "🥅",
    ":dizzy:": "💫",
    ":wastebasket:": "🗑️",
    ":passport_control:": "🛂",
    ":adhesive_bandage:": "🩹",
    ":monocle_face:": "🧐",
    ":coffin:": "⚰️",
    ":test_tube:": "🧪",
    ":necktie:": "👔",
    ":stethoscope:": "🩺",
    ":bricks:": "🧱",
    ":technologist:": "🧑\u200d💻",
    ":money_with_wings:": "💸",
    ":thread:": "🧵",
    ":safety_vest:": "🦺",
    ":airplane:": "✈️",
    ":t-rex:": "🦖",
}


def emojify(title: str) -> str:
    """Replace a leading gitmoji code like ":tada:" in a commit title with its unicode emoji.

    Unknown codes, and codes anywhere but at the start, are left as they are.
    """
    return re.sub(
        pattern=r"^(?P<emoji_code>:[\w_-]+:)",
        repl=lambda mo: GITMOJI_MAPPING.get(mo.group("emoji_code"), mo.group("emoji_code")),
        string=title,
    )


@dataclass
class CommitInfo:
    """Commit Information dataclass."""

    repo: pygit2.repository.Repository
    id: pygit2.Oid
    title: str
    """The commit message's first line, in full."""
    short_sha2: str
    utc_dt: dt.datetime
    tz: dt.timezone

    @property
    def short_title(self) -> str:
        """The commit message's first line, cut to 50 characters plus "..." when it's longer."""
        return self.title[0:50] + "..." if len(self.title) > 50 else self.title

    @property
    def emojified_title(self) -> str:
        """Emojified commit's short title.

        If title contains ":some_emoji_name:" then this replaces it with a corresponding unicode character
        (from gitmojis).

        Examples
        --------
        Commit's title: ':tada: Testing' -> `.emojified_title`: '🎉 Testing'
        """
        return emojify(self.short_title)

    @property
    def emojified_full_title(self) -> str:
        """Emojified commit's full title: the first line of its message, never cut.

        A leading ":some_emoji_name:" is replaced with the corresponding unicode character (from gitmojis).
        """
        return emojify(self.title)

    @property
    def dt_as_tz(self) -> dt.datetime:
        """Datetime `self.utc_dt` (UTC commit time creation) as `.astimezone`."""
        return self.utc_dt.astimezone(self.tz)

    @property
    def url(self) -> str:
        """Commit's url."""
        repo_url = self.repo.remotes["origin"].url or ""
        if repo_url.startswith("git@github.com:"):  # SSH remote
            repo_url = "https://github.com/" + repo_url.removeprefix("git@github.com:")
        return f"{repo_url.removesuffix('.git')}/commit/{self.id}"


def get_commit_info(repo: pygit2.repository.Repository, commit: pygit2.Commit) -> CommitInfo:
    """Get commit's `CommitInfo`."""
    title, _, _ = commit.message.partition("\n")
    return CommitInfo(
        repo=repo,
        id=commit.id,
        title=title,
        short_sha2=str(commit.id)[0:7],
        utc_dt=dt.datetime.fromtimestamp(commit.commit_time, dt.UTC),
        tz=dt.timezone(dt.timedelta(minutes=commit.commit_time_offset)),
    )


def get_latest_commits(limit: int = 5) -> list[CommitInfo]:
    """Get latest GitHub commits."""
    repo = pygit2.repository.Repository("./.git")
    commits = list(itertools.islice(repo.walk(repo.head.target, SortMode.TOPOLOGICAL), limit))
    return [get_commit_info(repo, c) for c in commits]


def get_last_commit() -> CommitInfo:
    """Get latest GitHub commit."""
    return next(iter(get_latest_commits(1)))


EXCLUDED_DIRS = frozenset({".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".ruff_cache"})


def count_lines(root: str | Path = ".") -> int:
    """Count all lines in .py files under `root`."""
    total = 0
    for dirpath, dirnames, filenames in Path(root).walk():
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in filenames:
            if name.endswith(".py"):
                try:
                    with (dirpath / name).open("rb") as f:
                        total += sum(1 for _ in f)
                except OSError:
                    continue
    return total
