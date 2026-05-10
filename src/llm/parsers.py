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

from pydantic import BaseModel, Field, ValidationError, field_validator


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class HaggleDecision(BaseModel):
    """The shape returned by the haggle JSON-mode prompt."""

    accept: bool
    counter_offer: int | None = None
    line: str = Field(min_length=1, max_length=400)
    walk_away: bool = False

    @field_validator("counter_offer")
    @classmethod
    def _non_negative_counter(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if v < 1:
            return 1
        return v


class Quest(BaseModel):
    """The shape returned by the quest-generation JSON-mode prompt."""

    title: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=400)
    target: str = Field(min_length=1, max_length=120)
    reward_gold: int = Field(ge=5, le=40)
    danger: str

    @field_validator("danger")
    @classmethod
    def _danger_enum(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in {"low", "medium", "high"}:
            return "low"
        return v


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
    """
    data = extract_json_object(raw)
    decision = HaggleDecision.model_validate(data)
    if decision.counter_offer is not None:
        clamped = max(persona_floor, min(persona_budget, decision.counter_offer))
        if clamped != decision.counter_offer:
            decision = decision.model_copy(update={"counter_offer": clamped})
    if decision.accept and offered_price > persona_budget:
        # Model accepted a price the persona literally cannot afford.
        decision = decision.model_copy(
            update={
                "accept": False,
                "counter_offer": persona_budget,
                "line": (
                    f"{decision.line} ...but I have only {persona_budget} gold "
                    "to my name."
                ),
            }
        )
    return decision


# ---------------------------------------------------------------------------
# Quest parsing
# ---------------------------------------------------------------------------
def parse_quest(raw: str) -> Quest:
    data = extract_json_object(raw)
    return Quest.model_validate(data)


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
)

DEGRADED_QUEST = Quest(
    title="A Quiet Errand",
    summary="The customer mumbles something about a missing pack near the road.",
    target="the road outside town",
    reward_gold=10,
    danger="low",
)
