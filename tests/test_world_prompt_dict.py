"""WorldState.to_prompt_dict exposes map coverage for quest generation."""

from __future__ import annotations

from src.game.world_state import WorldState


def test_prompt_dict_open_regions_with_no_active() -> None:
    ws = WorldState()
    d = ws.to_prompt_dict()
    assert d["map_regions_used_by_quests"] == []
    assert set(d["map_regions_open_for_new_quest"]) == {
        "mines",
        "town",
        "outskirts",
        "castle_hall",
    }
    assert "prefer these for NEW" in d["_quest_map_block"].lower() or "no open errand" in d[
        "_quest_map_block"
    ].lower()


def test_prompt_dict_marks_used_regions() -> None:
    ws = WorldState()
    ws.add_active_quest(
        {
            "title": "A",
            "summary": "s",
            "target": "t",
            "reward_gold": 10,
            "danger": "low",
            "location": "mines",
            "hotspot": "main_shaft",
        }
    )
    d = ws.to_prompt_dict()
    assert "mines" in d["map_regions_used_by_quests"]
    assert "mines" not in d["map_regions_open_for_new_quest"]
    assert len(d["map_regions_open_for_new_quest"]) == 3
