"""World state: the single shared bag of facts the LLM is conditioned on.

The world state is plain JSON and lives at ``data/savegame.json`` so that
the player (and the marker) can open it in any text editor and watch it
mutate while the game runs. This is intentional: it makes the LLM's
inputs visible during video evidence, and keeps the integration easy to
debug.

The class is small — load, save, mutate — and we explicitly do *not* try
to cache anything beyond the in-memory dict, because the rest of the
game treats writes as cheap and immediate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .world_map_data import (
    DEFAULT_HOTSPOT_ID,
    DEFAULT_LOCATION_ID,
    hotspot_ids,
    location_ids,
)


DEFAULT_PATH = Path("data") / "savegame.json"

# Reputation tracks player standing with three loose factions. Numbers
# stay in [-100, 100] for sanity. Used in prompts and in NPC spawn logic.
REPUTATION_KEYS = ("townsfolk", "wealthy", "underworld")
REP_CLAMP = (-100, 100)

# Gossip is a free-text list. We dedupe and cap so the prompt stays small.
MAX_GOSSIP = 20


@dataclass
class WorldState:
    """In-memory mirror of savegame.json. Mutate then call ``save()``."""

    path: Path = DEFAULT_PATH
    gold: int = 50
    reputation: dict[str, int] = field(default_factory=lambda: {k: 0 for k in REPUTATION_KEYS})
    gossip_heard: list[str] = field(default_factory=list)
    active_quests: list[dict[str, Any]] = field(default_factory=list)
    completed_quests: list[dict[str, Any]] = field(default_factory=list)
    served_personas: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: Path | str = DEFAULT_PATH) -> "WorldState":
        path = Path(path)
        if not path.exists():
            ws = cls(path=path)
            ws.save()
            return ws
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        rep = data.get("reputation", {}) or {}
        for k in REPUTATION_KEYS:
            rep.setdefault(k, 0)
        # Forward-migrate older saves that pre-date exploration mode by
        # filling in default location/hotspot on any active quest that
        # lacks them. Without this, quests written by older builds would
        # be impossible to complete in the new exploration flow.
        active = [_normalise_quest(q) for q in data.get("active_quests", [])]
        return cls(
            path=path,
            gold=int(data.get("gold", 50)),
            reputation=rep,
            gossip_heard=list(data.get("gossip_heard", [])),
            active_quests=active,
            completed_quests=list(data.get("completed_quests", [])),
            served_personas=list(data.get("served_personas", [])),
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "gold": self.gold,
            "reputation": self.reputation,
            "gossip_heard": self.gossip_heard,
            "active_quests": self.active_quests,
            "completed_quests": self.completed_quests,
            "served_personas": self.served_personas,
        }
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Mutators (game code calls these instead of poking attributes
    # directly so the prompt-relevant invariants stay enforced)
    # ------------------------------------------------------------------
    def add_gold(self, delta: int) -> None:
        self.gold = max(0, self.gold + int(delta))

    def adjust_reputation(self, faction: str, delta: int) -> None:
        if faction not in self.reputation:
            self.reputation[faction] = 0
        lo, hi = REP_CLAMP
        self.reputation[faction] = max(lo, min(hi, self.reputation[faction] + int(delta)))

    def add_gossip(self, line: str) -> bool:
        """Append a line of gossip if new. Returns True when added."""
        line = line.strip()
        if not line:
            return False
        if line in self.gossip_heard:
            return False
        self.gossip_heard.append(line)
        if len(self.gossip_heard) > MAX_GOSSIP:
            # Drop the oldest, not the newest, so prompts stay fresh.
            self.gossip_heard = self.gossip_heard[-MAX_GOSSIP:]
        return True

    def mark_persona_served(self, persona_id: str) -> None:
        if persona_id not in self.served_personas:
            self.served_personas.append(persona_id)

    def add_active_quest(self, quest: dict[str, Any]) -> None:
        self.active_quests.append(_normalise_quest(quest))

    def quests_at(self, location_id: str) -> list[dict[str, Any]]:
        """Active quests whose target hotspot is in ``location_id``."""
        return [q for q in self.active_quests if q.get("location") == location_id]

    def active_location_ids(self) -> set[str]:
        """Set of location ids that currently have at least one active quest."""
        return {q.get("location", DEFAULT_LOCATION_ID) for q in self.active_quests}

    def complete_quest(self, title: str) -> dict[str, Any] | None:
        for i, quest in enumerate(self.active_quests):
            if quest.get("title") == title:
                done = self.active_quests.pop(i)
                self.completed_quests.append(done)
                self.add_gold(int(done.get("reward_gold", 0)))
                return done
        return None

    # ------------------------------------------------------------------
    # Snapshot for prompts
    # ------------------------------------------------------------------
    def to_prompt_dict(self) -> dict[str, Any]:
        """The minimal view exposed to the LLM via prompts.py."""
        return {
            "gold": self.gold,
            "reputation": dict(self.reputation),
            "gossip_heard": list(self.gossip_heard),
            "active_quests": [q.get("title", "") for q in self.active_quests],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalise_quest(quest: dict[str, Any]) -> dict[str, Any]:
    """Ensure a quest dict has valid location/hotspot fields.

    Used both when loading older saves and when accepting a freshly
    parsed Quest, so the in-memory shape is always usable by the
    exploration scenes.
    """
    out = dict(quest)
    location = out.get("location", DEFAULT_LOCATION_ID)
    if location not in location_ids():
        location = DEFAULT_LOCATION_ID
    out["location"] = location
    valid = hotspot_ids(location)
    hotspot = out.get("hotspot", DEFAULT_HOTSPOT_ID)
    if hotspot not in valid:
        hotspot = valid[0]
    out["hotspot"] = hotspot
    return out
