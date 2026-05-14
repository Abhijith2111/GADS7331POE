"""Pydantic models and degrade logic for structured Ollama responses.

LLMs occasionally violate even strict JSON-mode constraints — they emit
extra prose, drop required fields, or hallucinate values outside our
allowed range. This module:

* validates each response against a Pydantic schema,
* clamps values that are *almost* right (e.g. negative gold, prices above
  the persona's coin purse),
* and provides ``call_with_retry`` which retries once and then degrades
  gracefully so the game never hangs on a broken model.

Game code only sees clean, typed dataclass-style objects.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from src.game.world_map_data import (
    DEFAULT_HOTSPOT_ID,
    DEFAULT_LOCATION_ID,
    hotspot_ids,
    location_ids,
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class HaggleDecision(BaseModel):
    """The shape returned by the haggle JSON-mode prompt.

    ``sale_gold`` is filled by ``parse_haggle`` when ``accept``; it is the
    amount the player receives and never exceeds the customer's budget.
    """

    model_config = ConfigDict(extra="ignore")

    accept: bool
    counter_offer: int | None = None
    line: str = Field(min_length=1, max_length=400)
    walk_away: bool = False
    agreed_price: int | None = Field(
        default=None,
        ge=1,
        description="When accept is true: gold the customer pays this round "
        "(may be below the listed ask). Omit to use the keeper's current ask.",
    )
    sale_gold: int = Field(default=0, ge=0)

    @field_validator("counter_offer")
    @classmethod
    def _non_negative_counter(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if v < 1:
            return 1
        return v

    @model_validator(mode="after")
    def _drop_agreed_when_not_accepting(self) -> "HaggleDecision":
        if not self.accept and self.agreed_price is not None:
            return self.model_copy(update={"agreed_price": None})
        return self


class FoundLine(BaseModel):
    """Tiny structured return from the post-quest "you found it" prompt."""

    line: str = Field(min_length=1, max_length=300)


class Quest(BaseModel):
    """The shape returned by the quest-generation JSON-mode prompt.

    ``location`` and ``hotspot`` were added to support the exploration
    mode: the LLM decides *where in the world* the player will find the
    target. Both fields are clamped to known values (see validators) so
    a wandering model can never produce an unreachable quest.
    """

    title: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=400)
    target: str = Field(min_length=1, max_length=120)
    reward_gold: int = Field(ge=5, le=40)
    danger: str
    location: str = DEFAULT_LOCATION_ID
    hotspot: str = DEFAULT_HOTSPOT_ID

    @field_validator("danger")
    @classmethod
    def _danger_enum(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in {"low", "medium", "high"}:
            return "low"
        return v

    @field_validator("location")
    @classmethod
    def _location_known(cls, v: str) -> str:
        v = v.strip().lower().replace(" ", "_")
        if v not in location_ids():
            return DEFAULT_LOCATION_ID
        return v

    @model_validator(mode="after")
    def _hotspot_in_location(self) -> "Quest":
        valid = hotspot_ids(self.location)
        if self.hotspot not in valid:
            # Clamp to the first hotspot of the chosen location.
            object.__setattr__(self, "hotspot", valid[0])
        return self


# ---------------------------------------------------------------------------
# Robust JSON extraction
# ---------------------------------------------------------------------------
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json_object(raw: str) -> dict[str, Any]:
    """Best-effort recovery of a single JSON object from a model reply.

    Ollama's ``format: json`` mode gives us clean JSON in the common case,
    but during prototyping we still saw stray prose, so we tolerate it
    here. Raises ``ValueError`` if no object can be recovered.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("empty response")
    # Fast path: the whole reply is JSON.
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Fallback: find the first {...} block.
    match = _JSON_OBJECT_RE.search(raw)
    if not match:
        raise ValueError("no JSON object in response")
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSON root is not an object")
    return parsed


# ---------------------------------------------------------------------------
# Haggle parsing + clamping
# ---------------------------------------------------------------------------
def parse_haggle(
    raw: str,
    *,
    offered_price: int,
    persona_budget: int,
    persona_floor: int,
) -> HaggleDecision:
    """Parse + clamp a haggle response.

    Out-of-range counter-offers are clamped into ``[persona_floor,
    persona_budget]`` rather than rejected outright; this keeps gameplay
    flowing when the model picks a number a coin or two off.

    When ``accept`` is true, ``sale_gold`` is how much gold the player
    receives: the model may set ``agreed_price`` below the keeper's
    current ask; otherwise ``sale_gold`` equals ``offered_price`` (capped
    by the customer's purse). If the ask exceeds the purse and the model
    did not name a lower ``agreed_price``, acceptance is demoted to a
    counter at ``persona_budget``.
    """
    data = extract_json_object(raw)
    decision = HaggleDecision.model_validate(data)
    if decision.counter_offer is not None:
        clamped = max(persona_floor, min(persona_budget, decision.counter_offer))
        if clamped != decision.counter_offer:
            decision = decision.model_copy(update={"counter_offer": clamped})

    if not decision.accept:
        return decision.model_copy(update={"sale_gold": 0})

    agreed = decision.agreed_price
    if offered_price > persona_budget and agreed is None:
        return decision.model_copy(
            update={
                "accept": False,
                "counter_offer": persona_budget,
                "line": (
                    f"{decision.line} ...but I have only {persona_budget} gold "
                    "to my name."
                ),
                "sale_gold": 0,
            }
        )

    base = agreed if agreed is not None else offered_price
    sale = max(1, min(int(base), persona_budget))
    return decision.model_copy(update={"sale_gold": sale})


# ---------------------------------------------------------------------------
# Quest parsing
# ---------------------------------------------------------------------------
def parse_quest(raw: str) -> Quest:
    data = extract_json_object(raw)
    return Quest.model_validate(data)


def parse_found_line(raw: str) -> FoundLine:
    data = extract_json_object(raw)
    return FoundLine.model_validate(data)


# ---------------------------------------------------------------------------
# Retry / degrade harness
# ---------------------------------------------------------------------------
def call_with_retry(
    call: Callable[[], str],
    parse: Callable[[str], Any],
    *,
    fallback: Any,
    retries: int = 1,
) -> tuple[Any, bool]:
    """Run ``call``+``parse``; on validation failure retry then degrade.

    Returns ``(value, ok)`` where ``ok`` is False if we fell back. Game
    code can use ``ok`` to display a "the customer hesitates..." beat
    rather than silently swallowing the error.
    """
    last_error: Exception | None = None
    for _ in range(retries + 1):
        try:
            raw = call()
            return parse(raw), True
        except (ValueError, ValidationError) as exc:
            last_error = exc
        except Exception as exc:  # noqa: BLE001 — surface as a degrade
            last_error = exc
            break
    # Attach the last error to the fallback if it has a `line` we can extend.
    if hasattr(fallback, "line") and last_error is not None:
        try:
            fallback = fallback.model_copy(
                update={"line": fallback.line + " (the customer pauses...)"}
            )
        except Exception:  # noqa: BLE001
            pass
    return fallback, False


# Default fallbacks used by call_with_retry callers.
DEGRADED_HAGGLE = HaggleDecision(
    accept=False,
    counter_offer=None,
    line="I... need a moment to think on it.",
    walk_away=False,
    sale_gold=0,
)

DEGRADED_QUEST = Quest(
    title="A Quiet Errand",
    summary="The customer mumbles something about a missing pack near the road.",
    target="the road outside town",
    reward_gold=10,
    danger="low",
    location=DEFAULT_LOCATION_ID,
    hotspot=DEFAULT_HOTSPOT_ID,
)

DEGRADED_FOUND = FoundLine(line="You find what they asked for, tucked away.")


# ---------------------------------------------------------------------------
# Quest target -> item phrase extraction
# ---------------------------------------------------------------------------
_ITEM_VERBS = (
    "find",
    "fetch",
    "recover",
    "retrieve",
    "bring back",
    "look for",
    "search for",
)


def extract_item_phrase(quest_summary: str) -> str:
    """Pick a short noun-phrase describing the quest item.

    Used by the "found it" prompt so the LLM has a concrete thing to
    mention. Falls back to ``"the item"`` if nothing matches; the prompt
    handles that gracefully.
    """
    text = quest_summary.strip()
    if not text:
        return "the item"
    lowered = text.lower()
    for verb in _ITEM_VERBS:
        idx = lowered.find(verb)
        if idx == -1:
            continue
        tail = text[idx + len(verb):].strip()
        # Strip leading articles to land on a clean noun.
        m = re.match(r"(my|the|a|an)\s+", tail, re.IGNORECASE)
        if m:
            tail = tail[m.end():]
        # Cut at the first sentence-ending punctuation or conjunction.
        cut = re.search(r"[,.;!\?]| for | from | in | at | near | so ", tail)
        if cut:
            tail = tail[: cut.start()]
        tail = tail.strip().strip('"')
        if 2 < len(tail) < 80:
            return f"the {tail}"
    return "the item"
