"""Three-slot save management and slot summaries for the main menu."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .paths import migrate_legacy_save_if_needed, save_slot_path
from .world_state import WorldState

SAVE_SLOT_COUNT = 3


@dataclass
class SaveSlotSummary:
    slot: int
    exists: bool
    gold: int = 0
    active_quests: int = 0
    rumour_memory: int = 0
    served_count: int = 0


def _read_save_payload(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def read_slot_summary(slot: int) -> SaveSlotSummary:
    path = save_slot_path(slot)
    data = _read_save_payload(path)
    if data is None:
        return SaveSlotSummary(slot=slot, exists=False)
    return SaveSlotSummary(
        slot=slot,
        exists=True,
        gold=int(data.get("gold", 0)),
        active_quests=len(data.get("active_quests", []) or []),
        rumour_memory=len(data.get("rumour_memory", []) or []),
        served_count=len(data.get("served_personas", []) or []),
    )


def all_slot_summaries() -> list[SaveSlotSummary]:
    migrate_legacy_save_if_needed()
    return [read_slot_summary(s) for s in range(1, SAVE_SLOT_COUNT + 1)]


def slot_has_save(slot: int) -> bool:
    return save_slot_path(slot).is_file()


def create_new_slot(slot: int) -> WorldState:
    """Fresh world state written to the given slot."""
    path = save_slot_path(slot)
    if path.is_file():
        path.unlink()
    ws = WorldState(path=path)
    ws.save()
    return ws


def load_slot(slot: int) -> WorldState:
    migrate_legacy_save_if_needed()
    return WorldState.load(save_slot_path(slot))
