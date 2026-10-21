"""Git, GitHub and some file/code counting Utilities.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

import abc
import asyncio
import datetime as dt
import itertools
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, override

import pygit2
from pygit2.enums import SortMode

if TYPE_CHECKING:
    from collections.abc import Iterator


__all__ = (
    "LinesCounter",
    "MatchingLinesCounter",
    "get_last_commit",
    "get_latest_commits",
)

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

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
    utc_dt: dt.datetime
    tz: dt.timezone

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
    def dt_as_tz(self) -> dt.datetime:
        """Datetime `self.utc_dt` (UTC commit time creation) as `.astimezone`."""
        return self.utc_dt.astimezone(self.tz)

    @property
    def url(self) -> str:
        """Commit's url."""
        if (repo_url := self.repo.remotes["origin"].url) is not None:
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
        utc_dt=dt.datetime.fromtimestamp(commit.commit_time).astimezone(dt.UTC),
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


IGNORED_DIRS = frozenset({".git", ".venv", "venv", "env", "__pycache__"})


@dataclass(kw_only=True)
class CodeCounter(abc.ABC):
    folder: str
    filetypes: str | tuple[str, ...]
    ignored_dirs: frozenset[str] = IGNORED_DIRS
    concurrency: int = 32

    _path: Path = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._path = Path(self.folder)

    def _iter_files(self) -> Iterator[Path]:
        for dirpath, dirnames, filenames in self._path.walk():
            dirnames[:] = [d for d in dirnames if d not in self.ignored_dirs]
            for name in filenames:
                if name.endswith(self.filetypes):
                    yield dirpath / name

    def _count_file(self, path: Path) -> int:
        try:
            with path.open(encoding="utf8") as f:
                return sum(1 for line in f if self.matches(line))
        except OSError, ValueError:
            log.warning("could not read %s", path, exc_info=True)
            return 0

    def _count_sync(self) -> int:
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            return sum(pool.map(self._count_file, self._iter_files()))

    async def count(self) -> int:
        return await asyncio.to_thread(self._count_sync)

    @abc.abstractmethod
    def matches(self, line: str) -> bool: ...


@dataclass(kw_only=True)
class LinesCounter(CodeCounter):
    """Lines Counter."""

    @override
    def matches(self, line: str) -> bool:
        return True


@dataclass(kw_only=True)
class MatchingLinesCounter(CodeCounter):
    """Matching Lines Counter."""

    substring: str

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.substring:
            msg = "substring must be non-empty"
            raise ValueError(msg)

    @override
    def matches(self, line: str) -> bool:
        return self.substring in line
