"""Tests for keeper rumour memory pools and save migration."""

from __future__ import annotations

import json
from pathlib import Path

from src.game.world_state import WorldState


def test_is_known_rumour_across_pools() -> None:
    ws = WorldState()
    ws.rumours_pending.append("They say the bard owes gold")
    assert ws.is_known_rumour("They say the bard owes gold")
    assert ws.is_known_rumour("  they   say   the bard owes gold  ")

    ws.rumour_memory.append("Word is the wizard hides a grimoire")
    assert ws.is_known_rumour("word is the wizard hides a grimoire")

    ws.gossip_heard.append("I heard the dwarf drinks alone")
    assert ws.is_known_rumour("I heard the dwarf drinks alone")


def test_add_rumour_overheard_skips_duplicates() -> None:
    ws = WorldState()
    assert ws.add_rumour_overheard("They say the inn is haunted")
    assert not ws.add_rumour_overheard("they say the inn is haunted")
    assert ws.rumours_pending == ["They say the inn is haunted"]


def test_commit_moves_pending_to_memory_and_town() -> None:
    ws = WorldState()
    line = "Rumour has it the noble cheats at dice"
    ws.add_rumour_overheard(line)
    assert ws.commit_rumour_to_memory(line)
    assert line not in ws.rumours_pending
    assert line in ws.rumour_memory
    assert line in ws.gossip_heard


def test_remove_from_memory() -> None:
    ws = WorldState()
    line = "They say the road is unsafe"
    ws.rumour_memory.append(line)
    ws.remove_from_memory(line)
    assert line not in ws.rumour_memory


def test_save_migration_populates_memory_from_legacy_gossip(tmp_path: Path) -> None:
    save_path = tmp_path / "savegame.json"
    payload = {
        "gold": 40,
        "reputation": {"townsfolk": 0, "wealthy": 0, "underworld": 0},
        "gossip_heard": ["Old rumour one", "Old rumour two"],
        "active_quests": [],
        "completed_quests": [],
        "served_personas": [],
    }
    save_path.write_text(json.dumps(payload), encoding="utf-8")
    ws = WorldState.load(save_path)
    assert ws.gossip_heard == ["Old rumour one", "Old rumour two"]
    assert ws.rumour_memory == ["Old rumour one", "Old rumour two"]
    assert ws.rumours_pending == []
