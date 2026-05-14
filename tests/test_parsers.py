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
    extract_item_phrase,
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
        assert d.sale_gold == 10

    def test_accept_uses_agreed_price_below_ask(self) -> None:
        raw = (
            '{"accept": true, "counter_offer": null, "line": "Seven.", '
            '"walk_away": false, "agreed_price": 7}'
        )
        d = parse_haggle(raw, **self._ctx(offered_price=10, persona_budget=12))
        assert d.accept is True
        assert d.sale_gold == 7

    def test_overpriced_acceptance_is_demoted(self) -> None:
        # Model accepts 100g but persona only has 12g — gameplay would soft-lock.
        raw = '{"accept": true, "counter_offer": null, "line": "Sure.", "walk_away": false}'
        d = parse_haggle(raw, **self._ctx(offered_price=100))
        assert d.accept is False
        assert d.counter_offer == 12  # clamped to budget
        assert d.sale_gold == 0

    def test_overpriced_with_agreed_within_budget_pays_agreed(self) -> None:
        raw = (
            '{"accept": true, "counter_offer": null, "line": "Eight is all I have.", '
            '"walk_away": false, "agreed_price": 8}'
        )
        d = parse_haggle(raw, **self._ctx(offered_price=100, persona_budget=12))
        assert d.accept is True
        assert d.sale_gold == 8

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
# Quest location/hotspot validators
# ---------------------------------------------------------------------------
class TestParseQuestLocation:
    """Exploration mode adds two clamped fields. These tests pin the
    behaviour: a wandering model can never make a quest unreachable,
    and an LLM that forgets the fields still produces a playable quest.
    """

    def _base_payload(self, **overrides):
        payload = {
            "title": "Find the Lost Lute",
            "summary": "Find my lost lute.",
            "target": "Pip's lute",
            "reward_gold": 12,
            "danger": "low",
            "location": "outskirts",
            "hotspot": "creek_bed",
        }
        payload.update(overrides)
        return payload

    def test_valid_location_and_hotspot(self) -> None:
        raw = json.dumps(self._base_payload(location="mines", hotspot="main_shaft"))
        q = parse_quest(raw)
        assert q.location == "mines"
        assert q.hotspot == "main_shaft"

    def test_hotspot_from_wrong_location_clamps(self) -> None:
        # "main_shaft" only exists in the mines, not the castle hall.
        raw = json.dumps(
            self._base_payload(location="castle_hall", hotspot="main_shaft")
        )
        q = parse_quest(raw)
        assert q.location == "castle_hall"
        # Falls back to the first hotspot of the chosen location.
        assert q.hotspot == "dais"

    def test_unknown_location_falls_back_to_default(self) -> None:
        raw = json.dumps(self._base_payload(location="atlantis", hotspot="anywhere"))
        q = parse_quest(raw)
        assert q.location == "outskirts"
        # Clamped to that location's first hotspot.
        assert q.hotspot == "broken_bridge"

    def test_missing_fields_fall_back_to_defaults(self) -> None:
        payload = self._base_payload()
        payload.pop("location")
        payload.pop("hotspot")
        q = parse_quest(json.dumps(payload))
        assert q.location == "outskirts"
        assert q.hotspot == "creek_bed"

    def test_location_normalised_to_snake_case(self) -> None:
        raw = json.dumps(
            self._base_payload(location="Castle Hall", hotspot="dais")
        )
        q = parse_quest(raw)
        assert q.location == "castle_hall"


# ---------------------------------------------------------------------------
# extract_item_phrase
# ---------------------------------------------------------------------------
class TestExtractItemPhrase:
    def test_simple_find(self) -> None:
        assert extract_item_phrase("Find my lute, will you?") == "the lute"

    def test_recover_phrase(self) -> None:
        out = extract_item_phrase("Recover the broken sword from the bandit camp.")
        assert out == "the broken sword"

    def test_fetch_with_article(self) -> None:
        assert extract_item_phrase("Fetch a barrel of ale") == "the barrel of ale"

    def test_falls_back_when_no_verb(self) -> None:
        assert extract_item_phrase("Just a friendly chat about the weather.") == "the item"

    def test_empty_summary(self) -> None:
        assert extract_item_phrase("") == "the item"

    def test_two_word_verb(self) -> None:
        assert (
            extract_item_phrase("Could you bring back the old ring?")
            == "the old ring"
        )


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
        assert result.sale_gold == 5

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
