# Copyright (C) 2020-present, Irene Adler ❤ (@Aluerie).
# Licensed under MPL-2.0, see the LICENSE file for details.
"""Stratz GraphQL Schemas."""

from __future__ import annotations

from typing import TypedDict

__all__ = ("AllItemsQuery",)


class AllItemsQuery(TypedDict):
    """Schema for Stratz GraphQL `get_items` response."""

    data: ItemData


class ItemData(TypedDict):
    constants: ItemConstants


class ItemConstants(TypedDict):
    items: list[Item]


class Item(TypedDict):
    id: int
    displayName: str
