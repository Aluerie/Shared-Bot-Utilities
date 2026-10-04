"""Git, GitHub and some file/code counting Utilities.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

import datetime
import itertools
import os
import re
from dataclasses import dataclass
from typing import override

import aiofiles
import pygit2
from pygit2.enums import SortMode

from shared.other import MISSING

__all__ = (
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


@dataclass
class CommitInfo:
    """Commit Information dataclass."""

    repo: pygit2.repository.Repository
    id: pygit2.Oid
    short_title: str
    short_sha2: str
    utc_dt: datetime.datetime
    tz: datetime.timezone

    @property
    def emojified_title(self) -> str | None:
        """Emojified commit's short title.

        If title contains ":some_emoji_name:" then this replaces it with a corresponding unicode character (from gitmojis).

        Example
        -------
        Commit's title: ':tada: Testing' -> `.emojified_title`: '🎉 Testing'
        """
        return re.sub(
            pattern=r"^(?P<emoji_code>:[\w_-]+:)",
            repl=lambda mo: GITMOJI_MAPPING.get(mo.group("emoji_code"), mo.group("emoji_code")),
            string=self.short_title,
        )

    @property
    def dt_as_tz(self) -> datetime.datetime:
        """Datetime `self.utc_dt` (UTC commit time creation) as `.astimezone`."""
        return self.utc_dt.astimezone(self.tz)

    @property
    def url(self) -> str:
        """Commit's url."""
        if repo_url := self.repo.remotes["origin"].url:
            repo_url = repo_url.removesuffix(".git")
        return f"{repo_url}/commit/{self.id}"


def get_commit_info(repo: pygit2.repository.Repository, commit: pygit2.Commit) -> CommitInfo:
    """Get commit's `CommitInfo`."""
    short, _, _ = commit.message.partition("\n")
    return CommitInfo(
        repo=repo,
        id=commit.id,
        short_title=short[0:50] + "..." if len(short) > 50 else short,
        short_sha2=str(commit.id)[0:7],
        utc_dt=datetime.datetime.fromtimestamp(commit.commit_time).astimezone(datetime.UTC),
        tz=datetime.timezone(datetime.timedelta(minutes=commit.commit_time_offset)),
    )


def get_latest_commits(limit: int = 5) -> list[CommitInfo]:
    """Get latest GitHub commits."""
    repo = pygit2.repository.Repository("./.git")
    commits = list(itertools.islice(repo.walk(repo.head.target, SortMode.TOPOLOGICAL), limit))
    return [get_commit_info(repo, c) for c in commits]


def get_last_commit() -> CommitInfo:
    """Get latest GitHub commit."""
    return next(iter(get_latest_commits(1)))


@dataclass
class CodeCounter:
    path: str
    filetype: str

    async def count(self, path: str = MISSING) -> int:
        lines = 0
        for i in os.scandir(path or self.path):
            if i.is_file():
                if i.path.endswith(self.filetype):
                    if re.search(r"(\\|/)?.?venv(\\|/)", i.path):
                        # Skip venv
                        continue
                    lines_list = await self.lines_list(i.path)
                    lines += await self.add_lines(lines_list)
            elif i.is_dir():
                lines += await self.count(i.path)
        return lines

    async def lines_list(self, path: str) -> list[str]:
        return (await (await aiofiles.open(path, encoding="utf8")).read()).split("\n")

    async def add_lines(self, lines_list: list[str]) -> int:
        raise NotImplementedError


@dataclass
class LinesCounter(CodeCounter):
    @override
    async def add_lines(self, lines_list: list[str]) -> int:
        return len(lines_list)


@dataclass
class ContainsCounter(CodeCounter):
    file_contains: str

    @override
    async def add_lines(self, lines_list: list[str]) -> int:
        return len([line for line in lines_list if self.file_contains in line])
