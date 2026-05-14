"""Tests for item haggle history helpers (no live LLM)."""

from __future__ import annotations

from src.game.npc import last_npc_counter


def test_last_npc_counter_empty() -> None:
    assert last_npc_counter([]) is None


def test_last_npc_counter_no_counter_field() -> None:
    hist = [
        {"price": 10, "line": "Too much.", "accepted": False},
    ]
    assert last_npc_counter(hist) is None


def test_last_npc_counter_uses_most_recent() -> None:
    hist = [
        {"price": 10, "line": "Eight.", "accepted": False, "npc_counter": 8},
        {"price": 9, "line": "Seven.", "accepted": False, "npc_counter": 7},
    ]
    assert last_npc_counter(hist) == 7


def test_last_npc_counter_skips_tail_without_counter() -> None:
    hist = [
        {"price": 10, "line": "Eight.", "accepted": False, "npc_counter": 8},
        {"price": 8, "line": "Hmm.", "accepted": False},
    ]
    assert last_npc_counter(hist) == 8
