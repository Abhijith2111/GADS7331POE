"""NPC abstraction: persona loading, conversation memory, spawn rotation."""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


PERSONA_DIR = Path("data") / "personas"


def personas_mentioned_in_text(
    text: str, personas: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return persona JSON dicts whose display name appears in ``text``.

    Matches full name as a substring (case-insensitive) or the first
    name as a whole word when it is at least 4 letters long (avoids
    matching short syllables like ``Ann`` inside other words).
    """
    lowered = text.lower()
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for p in personas:
        pid = str(p.get("id", ""))
        name = str(p.get("name", "")).strip()
        if not name or pid in seen:
            continue
        if name.lower() in lowered:
            out.append(p)
            seen.add(pid)
            continue
        first = name.split()[0]
        if len(first) >= 4 and re.search(
            r"\b" + re.escape(first.lower()) + r"\b", lowered
        ):
            out.append(p)
            seen.add(pid)
    return out


@dataclass
class NPC:
    """A single in-game customer.

    The conversation history is kept here, *not* inside the LLM client,
    so we can reset it cleanly when the customer leaves and so saving the
    game does not leak previous customers' chats.
    """

    persona: dict[str, Any]
    history: list[dict[str, str]] = field(default_factory=list)
    haggle_history: list[dict[str, Any]] = field(default_factory=list)
    served: bool = False

    @property
    def id(self) -> str:
        return str(self.persona["id"])

    @property
    def name(self) -> str:
        return str(self.persona["name"])

    def append_user(self, text: str) -> None:
        self.history.append({"role": "user", "content": text})

    def append_assistant(self, text: str) -> None:
        self.history.append({"role": "assistant", "content": text})

    def reset_chat(self) -> None:
        self.history.clear()
        self.haggle_history.clear()


# ---------------------------------------------------------------------------
# Persona loading
# ---------------------------------------------------------------------------
def load_personas(directory: Path = PERSONA_DIR) -> list[dict[str, Any]]:
    """Load every persona JSON in the directory, sorted by id."""
    personas: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        with open(path, "r", encoding="utf-8") as fh:
            personas.append(json.load(fh))
    if not personas:
        raise FileNotFoundError(
            f"No persona JSONs found in {directory}. "
            "Each NPC needs at least one persona file."
        )
    return personas


def load_persona_by_id(persona_id: str, directory: Path = PERSONA_DIR) -> dict[str, Any]:
    path = directory / f"{persona_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"persona '{persona_id}' not found at {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Spawn rotation
# ---------------------------------------------------------------------------
class CustomerQueue:
    """Picks the next customer to spawn.

    We bias *against* repeating the most recent persona so the player
    sees variety, but keep it stochastic so the game still surprises.
    """

    def __init__(self, personas: Iterable[dict[str, Any]], rng: random.Random | None = None) -> None:
        self.personas = list(personas)
        self.rng = rng or random.Random()
        self._last_id: str | None = None

    def next(self) -> NPC:
        if not self.personas:
            raise RuntimeError("CustomerQueue has no personas")
        candidates = [p for p in self.personas if p["id"] != self._last_id] or self.personas
        choice = self.rng.choice(candidates)
        self._last_id = choice["id"]
        return NPC(persona=choice)
