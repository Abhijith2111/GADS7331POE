"""Tests for src/llm/parsers.py.

We never call the live model in tests; everything is exercised against
canned JSON strings. The goal is to lock in the degrade/clamp behaviour
that the rest of the game depends on: gameplay must continue even when
the LLM violates the schema.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.llm.parsers import (
    DEGRADED_HAGGLE,
    DEGRADED_QUEST,
    HaggleDecision,
    Quest,
    call_with_retry,
    extract_json_object,
    parse_haggle,
    parse_quest,
)


# ---------------------------------------------------------------------------
# extract_json_object
# ---------------------------------------------------------------------------
class TestExtractJsonObject:
    def test_clean_json(self) -> None:
        raw = '{"accept": true, "counter_offer": null, "line": "ok", "walk_away": false}'
        assert extract_json_object(raw)["accept"] is True

    def test_recovers_from_leading_prose(self) -> None:
        raw = 'Here is your decision: {"accept": false, "counter_offer": 5, "line": "no", "walk_away": false}'
        assert extract_json_object(raw)["counter_offer"] == 5

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError):
            extract_json_object("")

    def test_no_object_raises(self) -> None:
        with pytest.raises(ValueError):
            extract_json_object("absolutely not json")

    def test_array_root_rejected(self) -> None:
        with pytest.raises(ValueError):
            extract_json_object("[1, 2, 3]")


# ---------------------------------------------------------------------------
# parse_haggle: the most safety-critical path
# ---------------------------------------------------------------------------
class TestParseHaggle:
    def _ctx(self, **overrides):
        ctx = {"offered_price": 10, "persona_budget": 12, "persona_floor": 4}
        ctx.update(overrides)
        return ctx

    def test_accepts_within_budget(self) -> None:
        raw = '{"accept": true, "counter_offer": null, "line": "Done.", "walk_away": false}'
        d = parse_haggle(raw, **self._ctx())
        assert d.accept is True
        assert d.counter_offer is None

    def test_overpriced_acceptance_is_demoted(self) -> None:
        # Model accepts 100g but persona only has 12g — gameplay would soft-lock.
        raw = '{"accept": true, "counter_offer": null, "line": "Sure.", "walk_away": false}'
        d = parse_haggle(raw, **self._ctx(offered_price=100))
        assert d.accept is False
        assert d.counter_offer == 12  # clamped to budget

    def test_counter_offer_clamped_to_floor(self) -> None:
        # Model proposes a counter below the persona's haggle floor.
        raw = '{"accept": false, "counter_offer": 1, "line": "Two coppers!", "walk_away": false}'
        d = parse_haggle(raw, **self._ctx(persona_floor=4))
        assert d.counter_offer == 4

    def test_counter_offer_clamped_to_budget(self) -> None:
        raw = '{"accept": false, "counter_offer": 999, "line": "Worth it.", "walk_away": false}'
        d = parse_haggle(raw, **self._ctx(persona_budget=12))
        assert d.counter_offer == 12

    def test_negative_counter_normalised_to_one_then_floor(self) -> None:
        raw = '{"accept": false, "counter_offer": -5, "line": "Pay me!", "walk_away": false}'
        d = parse_haggle(raw, **self._ctx(persona_floor=4))
        # Pydantic validator pushes negative to 1, then we clamp to floor.
        assert d.counter_offer == 4

    def test_missing_field_raises(self) -> None:
        raw = '{"accept": true, "counter_offer": null, "walk_away": false}'  # no line
        with pytest.raises(ValidationError):
            parse_haggle(raw, **self._ctx())

    def test_malformed_json_raises_value_error(self) -> None:
        raw = "not json at all"
        with pytest.raises(ValueError):
            parse_haggle(raw, **self._ctx())

    def test_extra_prose_around_json_recovered(self) -> None:
        raw = (
            'Sure thing, here you go:\n'
            '{"accept": false, "counter_offer": 8, "line": "How about eight?", '
            '"walk_away": false}\nThat is my offer.'
        )
        d = parse_haggle(raw, **self._ctx())
        assert d.counter_offer == 8


# ---------------------------------------------------------------------------
# parse_quest
# ---------------------------------------------------------------------------
class TestParseQuest:
    def test_valid(self) -> None:
        raw = json.dumps(
            {
                "title": "Find the Lost Lute",
                "summary": "Pip lost his lute. Find it before he sings about it.",
                "target": "the eastern bridge",
                "reward_gold": 12,
                "danger": "low",
            }
        )
        q = parse_quest(raw)
        assert q.danger == "low"
        assert q.reward_gold == 12

    def test_unknown_danger_demoted_to_low(self) -> None:
        raw = json.dumps(
            {
                "title": "X",
                "summary": "Y",
                "target": "Z",
                "reward_gold": 10,
                "danger": "EXTREME",
            }
        )
        assert parse_quest(raw).danger == "low"

    def test_reward_out_of_range_rejected(self) -> None:
        raw = json.dumps(
            {
                "title": "Greedy errand",
                "summary": "Y",
                "target": "Z",
                "reward_gold": 9999,
                "danger": "high",
            }
        )
        with pytest.raises(ValidationError):
            parse_quest(raw)

    def test_missing_field_rejected(self) -> None:
        raw = json.dumps(
            {
                "title": "X",
                "summary": "Y",
                "reward_gold": 10,
                "danger": "low",
            }
        )
        with pytest.raises(ValidationError):
            parse_quest(raw)


# ---------------------------------------------------------------------------
# call_with_retry: the degrade harness
# ---------------------------------------------------------------------------
class TestCallWithRetry:
    def test_first_call_succeeds(self) -> None:
        good = '{"accept": true, "counter_offer": null, "line": "Yes.", "walk_away": false}'
        result, ok = call_with_retry(
            call=lambda: good,
            parse=lambda raw: parse_haggle(
                raw, offered_price=5, persona_budget=10, persona_floor=2
            ),
            fallback=DEGRADED_HAGGLE,
        )
        assert ok is True
        assert isinstance(result, HaggleDecision)
        assert result.accept is True

    def test_retry_then_succeed(self) -> None:
        attempts = {"n": 0}

        def call() -> str:
            attempts["n"] += 1
            if attempts["n"] == 1:
                return "junk"  # fails parse
            return '{"accept": false, "counter_offer": 5, "line": "Maybe.", "walk_away": false}'

        result, ok = call_with_retry(
            call=call,
            parse=lambda raw: parse_haggle(
                raw, offered_price=10, persona_budget=12, persona_floor=4
            ),
            fallback=DEGRADED_HAGGLE,
        )
        assert ok is True
        assert attempts["n"] == 2
        assert result.counter_offer == 5

    def test_falls_back_after_retries(self) -> None:
        result, ok = call_with_retry(
            call=lambda: "still junk",
            parse=lambda raw: parse_haggle(
                raw, offered_price=10, persona_budget=12, persona_floor=4
            ),
            fallback=DEGRADED_HAGGLE,
        )
        assert ok is False
        assert isinstance(result, HaggleDecision)
        assert result.accept is False
        # The degrade harness annotates the fallback line.
        assert "pause" in result.line.lower()

    def test_quest_fallback_when_unparseable(self) -> None:
        result, ok = call_with_retry(
            call=lambda: "definitely not json",
            parse=parse_quest,
            fallback=DEGRADED_QUEST,
        )
        assert ok is False
        assert isinstance(result, Quest)
        assert result.reward_gold == 10
