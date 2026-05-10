# Prompt Archive

Every prompt iteration tested during development. Each entry lists the
prompt, an example output (good or bad), the verdict, and what we did
next. Entries are ordered chronologically so the iteration story is
visible in sequence.

> Prompts referenced as "current" are the ones still in
> `src/llm/prompts.py` at submission. Older iterations are kept here as
> evidence of the design process.

---

## A. Chat (free-form persona dialogue)

### A1 — First attempt: minimal persona, no rules

```
You are <name>, a customer in a tavern. Reply in character.
```

**Example reply (broke_bard, "tell me about yourself"):**
> "I am a bard. I sing songs and play the lute. As an AI language model, I cannot..."

**Verdict:** **failed**. Without explicit "do not break the fourth wall"
guidance, the smaller model leaked its self-identification. Rambling and
flat.

### A2 — Added strict character rules

```
You are role-playing a single customer in a fantasy tavern.
Stay strictly in character. Speak ONLY as this character, in first person.
Never narrate the scene, never use stage directions, never break the
fourth wall, never mention being an AI or a language model.
```

**Example reply (broke_bard, "tell me about yourself"):**
> "Pip Halloran, at your service. A wandering bard, mostly. Mostly broke,
> too. The road's been... unkind."

**Verdict:** **good**. No more AI-disclaimers. Voice still a bit
generic.

### A3 — Added persona card (current shape)

Persona facts are templated in via `_persona_card`:

```
--- Persona ---
Name: Pip Halloran
Voice and manner: rambling, self-pitying, fond of bad metaphors and
unsolicited verses
Private secret (DO NOT reveal unprompted): owes the thieves' guild
forty gold and is hiding from a collector
Coin purse (gold): 12
Currently wants: cheap_ale, a corner table out of sight, rumours of
caravan work
Starting attitude: anxious-but-friendly
```

**Example reply (broke_bard, "tell me about yourself"):**
> "Pip Halloran. Wandering bard. Picture me as... a candle in a draught.
> Always *almost* enough to read by. Got somewhere quiet to sit?"

**Verdict:** **excellent**. Voice is clearly the bard's. Naturally
hits the "wants a corner table" beat without it being obvious.

### A4 — Forbid stage directions in asterisks

After A3 we still saw replies like *"\*looks around nervously\*
Pip Halloran..."*. Added the explicit rule:

```
... never use stage directions in asterisks ...
```

**Verdict:** **fixed**. Asterisk stage directions disappeared.

### A5 — World-state injection (gossip carry-over)

We added a "Recent gossip already in town" block to the system prompt,
fed from `WorldState.gossip_heard`.

**Example with prior gossip "they say a courier rode through at dawn":**
> "Couriers, eh? They say a courier rode through at dawn — that yours?"

**Verdict:** **good**. Customer C references gossip that customer A
generated. World feels alive.

### A6 — Memory window of 6 turns

Earlier we kept the full chat history forever. After ~10 turns the
prompt got long and latency rose. Capped at 6 turns
(`CHAT_MEMORY_TURNS=6`).

**Verdict:** **good**. No visible degradation in coherence, prompt size
is bounded.

---

## B. Haggle (JSON-mode decisions)

### B1 — Free-text "yes/no"

First attempt asked for plain text and parsed with regex:

```
The shopkeeper offers <item> for <N> gold. Do you accept?
```

**Example reply:**
> "I'll accept it for 5, but only if you throw in a song."

**Verdict:** **failed**. Got conditional acceptances, ambiguous
counter-offers ("how about half that?"). Too brittle to parse.

### B2 — JSON in fenced code block

```
Reply with a JSON object inside a markdown code fence.
```

**Example reply:**
> ```json
> {"accept": false, "counter_offer": 5, "line": "Five, no more."}
> ```

**Verdict:** **partial**. The fence sometimes drifted; sometimes
the model added prose around it.

### B3 — `format: "json"` plus explicit schema (current)

We switched to Ollama's `format: "json"` mode and described the
schema *inside* the system prompt:

```
Reply with ONLY a JSON object matching this schema, no prose, no
markdown fences:
{
  "accept": boolean,
  "counter_offer": integer|null,
  "line": string,
  "walk_away": boolean
}
```

**Example reply:**
> `{"accept": false, "counter_offer": 4, "line": "Four. Final.", "walk_away": false}`

**Verdict:** **excellent**. ~98 % clean-parse rate on the default model
across our test suite. The 2 % goes through `extract_json_object`
recovery and never reaches the degrade path in practice.

### B4 — Explicit "fair price" and "absolute maximum" lines

Initially the prompt gave only `budget_gold`. The model accepted
unrealistic deals because it had no concept of "what is this item
*actually* worth to me".

```
Your private fair price (your floor): <floor> gold.
Your absolute maximum (coin purse): <budget> gold.
```

**Verdict:** **good**. Counter-offers cluster near the floor. Hard
clamps in `parse_haggle` catch the rare model that ignores the line.

### B5 — Negotiation history block

Added a small block listing previous offers and the customer's replies
in this negotiation:

```
--- Negotiation so far ---
  - Player offered 8 gold; you replied: "Eight? My grandmother..."
```

**Verdict:** **good**. The model now riffs on its earlier stance instead
of resetting between rounds.

---

## C. Quest (JSON-mode generation)

### C1 — Open-ended "give me a quest"

```
Generate a quest the customer asks the keeper to do.
```

**Example reply:**
> "Find the Crown of Eternal Frost in the Forgotten Catacombs of
> Y'haz'roth, beneath the cursed temple ..."

**Verdict:** **failed**. Wildly out of scale for a tavern errand.
Inconsistent reward values. Sometimes referenced modern objects
("an old phone").

### C2 — Constrained schema + range

```
- The quest must be plausible for a fantasy tavern errand.
- reward_gold must be a whole integer in [5, 40].
- Stay in the persona's voice in 'summary'.
- Never reference modern objects or real-world locations.
```

**Example reply (broke_bard):**
> `{"title":"A Lute Recovered","summary":"Find my lute, will you? Left
> it at the bridge; can't bring myself to look.","target":"the eastern
> bridge","reward_gold":10,"danger":"low"}`

**Verdict:** **excellent**. In voice. Plausibly tavern-scaled. Schema
reliable.

### C3 — Danger enum

Originally `danger` was free text: `"low"`, `"low/medium"`, `"medium-
ish"`, etc. Added enum coercion in the validator:

```python
if v not in {"low", "medium", "high"}: return "low"
```

**Verdict:** **good**. Game can colour quests by danger reliably.

---

## D. Failed experiments worth recording

### D1 — Asking the LLM to track gold itself

For one afternoon we let the chat prompt include "you may declare
gold gained" and parsed those declarations. The model invented and
duplicated transactions. Reverted: gold is mutated only by code.

### D2 — Single combined prompt for chat + haggle

We tried having the chat path optionally emit a haggle block at the
end (`<HAGGLE> ... </HAGGLE>`). It worked maybe 70 % of the time;
30 % of the time the closing tag was missing. Splitting into two
explicit endpoints fixed this completely.

### D3 — Higher temperature for variety

Pushed chat temperature to 1.2 in search of more flavour. Lines became
incoherent and broke character. Reverted to 0.8 (current default).

### D4 — Persona-specific system prompts per file

Idea: store the *whole* system prompt inside each persona JSON.
Rejected because: (a) it duplicates the rules across 5 files, so a
fix has to be repeated five times; (b) it lets a faulty persona file
silently disable the safety rules. Current shape — shared rules +
templated persona card — is safer and more maintainable.

---

## E. Iteration notes

- Around 60 % of prompt time was spent on the chat path's tone.
  Once the persona card shape settled, voices stabilised quickly.
- Around 30 % was on JSON-mode reliability — schema, enums, clamps.
- The remaining ~10 % was gossip detection (string heuristic) and
  retry/degrade plumbing.

The biggest qualitative leap was **A3 + A5 together**: persona card +
world-state block. With both in place, the customers feel embedded in
a world rather than dropped into an empty room.
