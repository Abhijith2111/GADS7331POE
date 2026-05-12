"""Tests for persona name detection inside gossip strings."""

from __future__ import annotations

from src.game.npc import personas_mentioned_in_text

_FIXTURE = [
    {"id": "broke_bard", "name": "Pip Halloran"},
    {"id": "paranoid_wizard", "name": "Elara Voss"},
    {"id": "gruff_dwarf", "name": "Brom Ironfoot"},
]


def test_full_name_substring() -> None:
    t = "They say Pip Halloran owes the guild forty gold."
    out = personas_mentioned_in_text(t, _FIXTURE)
    ids = [p["id"] for p in out]
    assert ids == ["broke_bard"]


def test_first_name_word_boundary() -> None:
    t = "I heard Elara muttering about debts near the docks."
    out = personas_mentioned_in_text(t, _FIXTURE)
    assert [p["id"] for p in out] == ["paranoid_wizard"]


def test_multiple_people() -> None:
    t = "Brom Ironfoot told me Pip Halloran skipped town."
    out = personas_mentioned_in_text(t, _FIXTURE)
    ids = sorted(p["id"] for p in out)
    assert ids == ["broke_bard", "gruff_dwarf"]


def test_no_match() -> None:
    t = "The weather has been unseasonably warm."
    assert personas_mentioned_in_text(t, _FIXTURE) == []
