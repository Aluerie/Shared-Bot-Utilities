# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Tests for ``shared.fuzzy``."""

from shared import fuzzy

HEROES = ["Anti-Mage", "Axe", "Bane", "Crystal Maiden", "Dark Willow", "Dawnbreaker"]


def test_ratios_are_scores_from_0_to_100() -> None:
    assert fuzzy.ratio("axe", "axe") == 100
    assert fuzzy.ratio("abc", "xyz") == 0
    assert fuzzy.partial_ratio("maiden", "Crystal maiden") == 100
    assert fuzzy.token_sort_ratio("maiden crystal", "Crystal Maiden") == 100


def test_extract_orders_by_score_and_limits() -> None:
    matches = fuzzy.extract("Dawn", HEROES, limit=3)
    assert len(matches) == 3
    assert matches[0][0] == "Dawnbreaker"
    scores = [score for _, score in matches]
    assert scores == sorted(scores, reverse=True)


def test_extract_with_dict_returns_values() -> None:
    choices = {"axe": 2, "bane": 3}
    assert fuzzy.extract("axe", choices, limit=1) == [("axe", 100, 2)]


def test_extract_one() -> None:
    assert fuzzy.extract_one("Crystal", HEROES, scorer=fuzzy.partial_ratio) == ("Crystal Maiden", 100)
    assert fuzzy.extract_one("anything", []) is None
    assert fuzzy.extract_one("axe", HEROES, score_cutoff=101) is None


def test_extract_or_exact_prefers_exact_match() -> None:
    assert fuzzy.extract_or_exact("Axe", HEROES) == [("Axe", 100)]


def test_extract_top_matches_keeps_ties_only() -> None:
    matches = fuzzy.extract_top_matches("a", ["a", "a", "b"])
    assert matches == [("a", 100), ("a", 100)]


def test_finder() -> None:
    # case-insensitive, the shortest match comes first: "Daw" in Dawnbreaker beats "Dark W" in Dark Willow
    assert fuzzy.finder("dw", HEROES) == ["Dawnbreaker", "Dark Willow"]
    assert fuzzy.find_one("cm", HEROES) == "Crystal Maiden"
    assert fuzzy.find_one("zzz", HEROES) is None
