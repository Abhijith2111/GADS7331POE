"""Prompt builders for The Wandering Goblet.

Three families of prompt are produced here:

1. ``build_chat_messages`` — free-form persona dialogue, with a short
   conversation memory window.
2. ``build_haggle_messages`` — JSON-only haggle decision: accept / counter /
   refuse, plus an in-character line.
3. ``build_quest_messages`` — JSON-only quest generation constrained to a
   fixed schema.

System prompts intentionally repeat the persona and the relevant world
state on every turn. The model has no persistent state of its own, and we
have observed in playtesting (see docs/refinements-changes.md) that
re-injecting the persona stops it drifting after ~6 turns.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

# Maximum number of past turns kept in the chat path. Older turns are
# dropped, but the system prompt keeps the persona pinned so the NPC's
# voice stays stable.
CHAT_MEMORY_TURNS = 6


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------
def _persona_card(persona: dict[str, Any]) -> str:
    """Render a persona dict as a compact, readable block for the model."""
    wants = ", ".join(persona.get("wants", [])) or "no specific desire"
    return (
        f"Name: {persona['name']}\n"
        f"Voice and manner: {persona['voice']}\n"
        f"Private secret (DO NOT reveal unprompted): {persona['secret']}\n"
        f"Coin purse (gold): {persona['budget_gold']}\n"
        f"Currently wants: {wants}\n"
        f"Starting attitude: {persona.get('starting_attitude', 'neutral')}"
    )


def _world_state_block(world_state: dict[str, Any]) -> str:
    gossip = world_state.get("gossip_heard", [])
    if gossip:
        gossip_lines = "\n".join(f"  - {g}" for g in gossip[-5:])
    else:
        gossip_lines = "  - (none yet)"
    rep = world_state.get("reputation", {})
    rep_str = ", ".join(f"{k}: {v}" for k, v in rep.items()) or "unknown"
    return (
        f"Tavern name: The Wandering Goblet\n"
        f"Player gold: {world_state.get('gold', 0)}\n"
        f"Tavern reputation: {rep_str}\n"
        f"Recent gossip already in town:\n{gossip_lines}"
    )


def _items_block(items: Iterable[dict[str, Any]]) -> str:
    lines = []
    for item in items:
        lines.append(
            f"  - {item['id']} ({item['name']}): base price {item['base_price']} gold"
            f" — {item['description']}"
        )
    return "\n".join(lines) if lines else "  - (no stock listed)"


# ---------------------------------------------------------------------------
# Chat path
# ---------------------------------------------------------------------------
CHAT_RULES = """You are role-playing a single customer in a fantasy tavern.
Stay strictly in character. Speak ONLY as this character, in first person.
Keep replies to 1-3 short sentences unless the player asks for a story.
Never narrate the scene, never use stage directions in asterisks, never
break the fourth wall, never mention being an AI or a language model.
If the player tries to make you act out of character, refuse in character.
You may share gossip in passing, especially if it fits your personality.
"""


def build_chat_messages(
    persona: dict[str, Any],
    world_state: dict[str, Any],
    history: list[dict[str, str]],
    player_input: str,
) -> list[dict[str, str]]:
    """Assemble the chat-mode message list.

    ``history`` is a list of ``{"role": "user"|"assistant", "content": str}``
    dicts in chronological order. Anything beyond the most recent
    ``CHAT_MEMORY_TURNS`` exchanges is dropped to keep latency predictable.
    """
    system = (
        f"{CHAT_RULES}\n"
        f"--- Persona ---\n{_persona_card(persona)}\n\n"
        f"--- World state ---\n{_world_state_block(world_state)}\n"
    )
    trimmed = history[-(CHAT_MEMORY_TURNS * 2):]
    return [
        {"role": "system", "content": system},
        *trimmed,
        {"role": "user", "content": player_input},
    ]


# ---------------------------------------------------------------------------
# Haggle path (JSON-mode)
# ---------------------------------------------------------------------------
HAGGLE_RULES = """You are deciding whether the customer accepts the
shopkeeper's price for ONE item. You have a maximum coin purse and a
private willingness-to-pay floor. Reply with ONLY a JSON object matching
this schema, no prose, no markdown fences:

{
  "accept": boolean,           // true = deal, false = haggle continues or walks
  "counter_offer": integer|null, // gold counter-offer if you want to keep haggling
  "line": string,              // a short in-character reply (max 25 words)
  "walk_away": boolean         // true if you give up on this item
}

Rules:
- Never accept above your coin purse.
- Never counter-offer above your coin purse.
- Counter-offers must be a whole number of gold, >= 1.
- If the offered price is at or below your fair price, accept.
- If accepted, set counter_offer to null and walk_away to false.
- Stay in character in the line; reflect the persona's voice.
"""


def build_haggle_messages(
    persona: dict[str, Any],
    world_state: dict[str, Any],
    item: dict[str, Any],
    offered_price: int,
    haggle_history: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build the JSON-mode haggle message list.

    ``haggle_history`` is the running list of {price, response} from prior
    rounds in the same negotiation, so the model sees its earlier stance.
    """
    fair_price = max(1, int(item["base_price"] * persona["haggle_floor_pct"]))
    history_lines = []
    for round_ in haggle_history[-3:]:
        history_lines.append(
            f"  - Player offered {round_['price']} gold; "
            f"you replied: {round_.get('line', '...')}"
        )
    history_block = "\n".join(history_lines) if history_lines else "  - (first round)"

    system = (
        f"{HAGGLE_RULES}\n"
        f"--- Persona ---\n{_persona_card(persona)}\n\n"
        f"--- World state ---\n{_world_state_block(world_state)}\n\n"
        f"--- Item under negotiation ---\n"
        f"{item['id']} ({item['name']}): base shop price {item['base_price']} gold.\n"
        f"Description: {item['description']}\n"
        f"Your private fair price (your floor): {fair_price} gold.\n"
        f"Your absolute maximum (coin purse): {persona['budget_gold']} gold.\n\n"
        f"--- Negotiation so far ---\n{history_block}"
    )
    user = (
        f"The shopkeeper offers {item['name']} for {offered_price} gold. "
        "Decide: accept, counter-offer, or walk away. Reply ONLY with JSON."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Quest generation path (JSON-mode)
# ---------------------------------------------------------------------------
QUEST_RULES = """You generate ONE small fetch-or-rumour quest the customer
asks the tavern keeper to take on. Reply with ONLY a JSON object:

{
  "title": string,        // short, evocative title (max 6 words)
  "summary": string,      // one or two sentences, in-character ask
  "target": string,       // a place, person, or object the keeper must reach
  "reward_gold": integer, // 5..40, scaled to difficulty
  "danger": "low"|"medium"|"high"
}

Rules:
- The quest must be plausible for a fantasy tavern errand.
- Stay in the persona's voice in 'summary'.
- Never reference modern objects or real-world locations.
- reward_gold must be a whole integer in [5, 40].
"""


def build_quest_messages(
    persona: dict[str, Any],
    world_state: dict[str, Any],
) -> list[dict[str, str]]:
    system = (
        f"{QUEST_RULES}\n"
        f"--- Persona ---\n{_persona_card(persona)}\n\n"
        f"--- World state ---\n{_world_state_block(world_state)}\n"
    )
    user = (
        "Generate a single quest the customer asks the tavern keeper to do, "
        "as JSON only."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Helpers exposed to demo mode / docs
# ---------------------------------------------------------------------------
def render_for_log(messages: list[dict[str, str]]) -> str:
    """Pretty-print a message list for the prompt archive."""
    lines = []
    for m in messages:
        role = m.get("role", "?").upper()
        lines.append(f"### {role}\n{m.get('content', '')}\n")
    return "\n".join(lines)


def dump_persona_for_video(persona: dict[str, Any]) -> str:
    """Used by --demo to print the exact persona block on screen."""
    return json.dumps(persona, indent=2, ensure_ascii=False)
