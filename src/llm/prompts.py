"""Prompt builders for The Tavern Master.

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

from src.game.world_map_data import render_locations_for_prompt

# Maximum number of past turns kept in the chat path. Older turns are
# dropped, but the system prompt keeps the persona pinned so the NPC's
# voice stays stable.
CHAT_MEMORY_TURNS = 6

# Shown only in the haggle prompt so the model varies accept/counter by persona.
_DEFAULT_HAGGLE_BEHAVIOR = (
    "Balanced: you want a reasonable discount but won't waste the evening "
    "over a few gold."
)


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

    # Quest + map coverage (filled by ``WorldState.to_prompt_dict``).
    quest_map = world_state.get("_quest_map_block", "").strip()
    if quest_map:
        quest_map = f"\n{quest_map}\n"
    else:
        quest_map = ""

    return (
        f"Tavern name: The Tavern Master\n"
        f"Player gold: {world_state.get('gold', 0)}\n"
        f"Tavern reputation: {rep_str}\n"
        f"Recent gossip already in town:\n{gossip_lines}"
        f"{quest_map}"
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
private willingness-to-pay anchor (your "fair price"). Reply with ONLY a
JSON object matching this schema, no prose, no markdown fences:

{
  "accept": boolean,           // true = deal, false = haggle continues or walks
  "counter_offer": integer|null, // gold counter-offer if you want to keep haggling
  "line": string,              // a short in-character reply (max 25 words)
  "walk_away": boolean,        // true if you give up on this item
  "agreed_price": integer|null // if accept is true: gold you actually pay the keeper
                                 // this round (must be <= current ask if lower).
                                 // Use null if you accept the keeper's listed price exactly.
}

Rules:
- Never accept above your coin purse.
- Never counter-offer above your coin purse.
- Counter-offers must be a whole number of gold, >= 1.
- Follow **your haggling temperament** (in the Persona block): generous or
  rushed customers may accept at or even slightly above the listed fair price
  to save time, pride, or hassle; tight-fisted ones push below it, counter
  hard, or walk away over small sums.
- Use your fair price as a guide: it is the usual ceiling for a "good deal"
  for *you*, but temperament can bend it (never above purse).
- If you accept, set counter_offer to null, walk_away to false, and set
  agreed_price to the exact gold you pay (or null only if you pay the keeper's
  current ask with no change).
- **Handshake:** If the negotiation history shows *you* countered with a
  specific gold amount and the keeper's *current* offer equals that amount,
  you MUST accept (accept: true) at that price unless you walk_away. Do not
  counter again at the same price you already named.
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

    ``haggle_history`` is the running list of prior rounds (price, line,
    optional npc_counter for your last counter-offer gold).
    """
    fair_price = max(1, int(item["base_price"] * persona["haggle_floor_pct"]))
    haggle_behavior = (
        str(persona.get("haggle_behavior") or "").strip() or _DEFAULT_HAGGLE_BEHAVIOR
    )
    history_lines = []
    for round_ in haggle_history[-3:]:
        nc = round_.get("npc_counter")
        line = round_.get("line", "...")
        if nc is not None:
            history_lines.append(
                f"  - Player offered {round_['price']} gold; you countered {nc} gold — "
                f"\"{line}\""
            )
        else:
            history_lines.append(
                f"  - Player offered {round_['price']} gold; you replied: {line}"
            )
    history_block = "\n".join(history_lines) if history_lines else "  - (first round)"

    system = (
        f"{HAGGLE_RULES}\n"
        f"--- Persona ---\n{_persona_card(persona)}\n"
        f"Haggling temperament: {haggle_behavior}\n\n"
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
# Gossip-buying path (JSON-mode, re-uses HaggleDecision schema)
# ---------------------------------------------------------------------------
GOSSIP_BUY_RULES = """The tavern keeper is offering to sell you a piece of
gossip that is circulating about YOU personally, for a price in gold. You
are deciding whether to pay so you can hear what's being said. Reply with
ONLY a JSON object matching this schema, no prose, no markdown fences:

{
  "accept": boolean,           // true = pay the keeper, false = haggle continues or refuse
  "counter_offer": integer|null, // your counter price in gold (omit on accept)
  "line": string,              // a short in-character reply (max 25 words)
  "walk_away": boolean,        // true if the rumour is not worth paying for
  "agreed_price": integer|null // if accept: exact gold you pay (null = keeper's ask)
}

Rules:
- The rumour is ABOUT YOU. Decide based on how much it might damage you.
- Never accept above your coin purse.
- Counter-offers must be a whole number of gold, >= 1.
- If you accept, set counter_offer to null and agreed_price to what you pay
  (or null if you pay the keeper's listed price exactly).
- If the rumour reveals your secret or names you directly, value it more.
- If the rumour is vague or harmless, walk away (set walk_away=true).
- Stay strictly in character; reflect your voice and your starting attitude.
- The keeper is selling YOU on YOU; do not pretend the rumour is about
  someone else.
"""


def build_gossip_buy_messages(
    persona: dict[str, Any],
    world_state: dict[str, Any],
    rumour_text: str,
    offered_price: int,
) -> list[dict[str, str]]:
    """Build the JSON-mode prompt for a sell-the-rumour negotiation.

    The reply schema deliberately matches haggling (``HaggleDecision``)
    so the existing ``parse_haggle`` clamping logic re-applies here.
    The persona's ``budget_gold`` is the hard ceiling; the floor is set
    low so the model can take an attractive bargain.
    """
    system = (
        f"{GOSSIP_BUY_RULES}\n"
        f"--- Persona ---\n{_persona_card(persona)}\n\n"
        f"--- World state ---\n{_world_state_block(world_state)}\n\n"
        f"--- Rumour the keeper claims to have heard about YOU ---\n"
        f"\"{rumour_text}\"\n\n"
        f"--- Your coin purse ---\n"
        f"You can pay at most {persona['budget_gold']} gold.\n"
    )
    user = (
        f"The keeper offers to whisper this rumour about you for "
        f"{offered_price} gold. Decide: pay, counter-offer, or walk "
        "away. Reply ONLY with JSON."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


GOSSIP_INTEL_RULES = """The tavern keeper is offering to sell you a piece
of gossip circulating in the bar — NOT about you, but about one or more
named locals you may care about (rivals, debtors, lovers, authorities).
You are deciding whether to pay the asking price to hear it. Reply with
ONLY a JSON object matching this schema, no prose, no markdown fences:

{
  "accept": boolean,
  "counter_offer": integer|null,
  "line": string,
  "walk_away": boolean,
  "agreed_price": integer|null // if accept: exact gold you pay (null = keeper's ask)
}

Rules:
- Never accept above your coin purse; never counter above your purse.
- If you accept, set counter_offer to null and agreed_price to what you pay
  (or null if you pay the keeper's listed price exactly).
- If the rumour sounds juicy, actionable, or damaging to someone you
  dislike, you may pay. If it sounds dull or irrelevant, walk away.
- Stay strictly in character.
- The subjects named in the rumour are other people — not you.
"""


def build_gossip_intel_messages(
    persona: dict[str, Any],
    world_state: dict[str, Any],
    subject_names: str,
    rumour_text: str,
    offered_price: int,
) -> list[dict[str, str]]:
    """JSON-mode prompt: sell third-party intel to the current customer."""
    system = (
        f"{GOSSIP_INTEL_RULES}\n"
        f"--- Persona ---\n{_persona_card(persona)}\n\n"
        f"--- World state ---\n{_world_state_block(world_state)}\n\n"
        f"--- Who the rumour is ABOUT (not you) ---\n"
        f"{subject_names}\n\n"
        f"--- The rumour (as the keeper would tell it) ---\n"
        f"\"{rumour_text}\"\n\n"
        f"--- Your coin purse ---\n"
        f"You can pay at most {persona['budget_gold']} gold.\n"
    )
    user = (
        f"The keeper offers this intelligence about {subject_names} for "
        f"{offered_price} gold. Decide: pay, counter-offer, or walk "
        "away. Reply ONLY with JSON."
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
  "danger": "low"|"medium"|"high",
  "location": string,     // one of the location ids listed below
  "hotspot": string       // one of THAT location's hotspot ids
}

Rules:
- The quest must be plausible for a fantasy tavern errand.
- Stay in the persona's voice in 'summary'.
- Never reference modern objects or real-world locations.
- reward_gold must be a whole integer in [5, 40].
- 'location' must be one of the ids in the Locations table below.
- 'hotspot' MUST be one of the hotspot ids listed under that location.
- Pick a location/hotspot pair that fits the narrative target -- if the
  target is a missing pickaxe, the mines fit better than the castle.
- **Spread work across the map.** The four regions are `mines`, `town`,
  `outskirts`, and `castle_hall`. If the world state lists regions that
  do NOT yet have an open errand, strongly prefer setting THIS quest's
  `location` to one of those unused regions whenever the story still makes
  sense. Do not default every quest to the same region out of habit.
  Only reuse a region that already has an open errand if the target truly
  could not plausibly be anywhere else.
"""


def build_quest_messages(
    persona: dict[str, Any],
    world_state: dict[str, Any],
) -> list[dict[str, str]]:
    open_regions = world_state.get("map_regions_open_for_new_quest") or []
    used_regions = world_state.get("map_regions_used_by_quests") or []
    hint = ""
    if open_regions:
        hint = (
            f" Prefer `location` one of: {', '.join(open_regions)} "
            f"— those map areas have no open errand yet. "
        )
    elif used_regions and len(used_regions) >= 4:
        hint = " Every region already has work queued; any location is fine. "

    system = (
        f"{QUEST_RULES}\n"
        f"--- Persona ---\n{_persona_card(persona)}\n\n"
        f"--- World state ---\n{_world_state_block(world_state)}\n\n"
        f"--- Locations available in this game ---\n"
        f"{render_locations_for_prompt()}\n"
    )
    user = (
        "Generate a single quest the customer asks the tavern keeper to do, "
        "as JSON only. Remember to fill in 'location' and 'hotspot' from "
        f"the table above. {hint}"
        "Vary the map region from this customer's earlier errands when possible."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Found-it path (JSON-mode, called once per successful quest)
# ---------------------------------------------------------------------------
FOUND_RULES = """You write ONE short narrative line describing the moment
the tavern keeper finds the item the customer asked for. Reply with ONLY
a JSON object:

{
  "line": string   // 1-2 sentences, max 40 words, second-person voice
}

Rules:
- Speak to the keeper as the narrator: "You spot...", "You ease open...".
- Mention the item phrase given below at least once.
- Mention the location and the specific spot in the same line.
- Do NOT mention being an AI, do NOT use stage directions.
- No prose outside the JSON object.
"""


def build_found_messages(
    persona: dict[str, Any],
    world_state: dict[str, Any],
    quest: dict[str, Any],
    location_name: str,
    hotspot_name: str,
    item_phrase: str,
) -> list[dict[str, str]]:
    """Build the JSON-mode prompt for the 'you found it' beat."""
    system = (
        f"{FOUND_RULES}\n"
        f"--- Quest-giver persona ---\n{_persona_card(persona)}\n\n"
        f"--- World state ---\n{_world_state_block(world_state)}\n\n"
        f"--- Quest in progress ---\n"
        f"Title: {quest.get('title', 'A Quiet Errand')}\n"
        f"Summary: {quest.get('summary', '')}\n"
        f"Target as the customer described it: {quest.get('target', '')}\n"
    )
    user = (
        f"The keeper has just reached the {hotspot_name} at {location_name} "
        f"and located {item_phrase}. Write the in-the-moment narration as "
        "JSON only."
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
