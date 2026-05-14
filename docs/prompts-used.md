# Prompt & development archive — The Tavern Master

This file is the **single archive** for the project:

1. **Part I — What you asked Cursor to add** (features, UI, tooling, docs, Git), with outcomes and provenance.
2. **Part II — In-game LLM prompt testing** (Ollama): iterations, example outputs, verdicts, and reasoning.

The game shipped under the working title **The Wandering Goblet** until it was **renamed to The Tavern Master** (see [refinements-changes.md](refinements-changes.md)). Older transcripts and commits may still use the former name.

**Related docs:** [llm-integration-report.md](llm-integration-report.md) (integration overview), [refinements-changes.md](refinements-changes.md) (dated engineering log). **Source of truth for live prompts:** `src/llm/prompts.py`.

---

## How to maintain this file

- After a **significant Cursor session**, append a row to **Part I** (and, if you changed prompt text, a bullet under **Part II**).
- **Provenance tags:** `transcript` = recovered from a Cursor agent transcript JSONL; `refinements` = summarized from [refinements-changes.md](refinements-changes.md); `git` = inferred from commit message only; `(reconstructed)` = best-effort memory when no primary source was available.
- **Cursor transcripts** for this project live outside the repo (e.g. under the IDE’s `agent-transcripts` folder for this workspace). They are not auto-synced to Git.

### Template — Part I row

```text
| YYYY-MM-DD | One-line request | shipped / partial / n/a (support only) | key files or commits | provenance; short notes |
```

### Template — Part II prompt test

```text
### Xn — Short title
**Prompt / change:** …
**Example (good or bad):** …
**Verdict:** …
**Reasoning / next step:** …
```

---

## Part I — Development request history (Cursor asks → outcomes)

Requests are listed in **chronological order** (oldest first). Duplicate “please push to GitHub” lines are folded into the nearest feature row where obvious.

| Date | Request (summary) | Outcome | Key files / commits | Provenance & notes |
|------|-------------------|---------|---------------------|-------------------|
| 2026-05-10 | Assignment brief: standalone game with **local LLM via Ollama**, reproducible integration, documentation (high concept, integration report, etc.) | Scoped course project; chose tavern sim + Pygame + Ollama | Full repo, `docs/*` | transcript; first user message in thread |
| 2026-05-10 | **Implement “The Tavern Master”** initial plan (scaffold through docs; transcripts use *The Wandering Goblet*) | Shipped playable prototype + docs + tests | `src/`, `docs/`, `data/` | transcript |
| 2026-05-11 | **How do I run the game / pull model / step 3 / Python not found** | Support & doc paths clarified | `README.md`, `docs/setup.md` | transcript; no feature code |
| 2026-05-11 | **Pygame `pip install` fails** on Windows (source build / distutils) | Switched dependency to **pygame-ce** | `requirements.txt`, `docs/setup.md` | transcript + refinements |
| 2026-05-11 | **More transparent** AI reply area; **player + name tag above** dialogue | UI updated | `src/game/*`, `src/main.py` | transcript; commit `e67bb7e` |
| 2026-05-11 | **Side action buttons** instead of only slash commands | Action panel + modals; slash kept as shortcut | `src/main.py`, `src/game/ui.py` | transcript; `8a354f1` |
| 2026-05-11 | **Easier launch** than PowerShell every time | `.bat` one-click launchers | `run_game.bat`, `setup.bat` | transcript; `1c4b79f` |
| 2026-05-11 | **Remove the line from NPC faces** | Portrait highlight tweak | `src/game/scene.py` (per commit) | transcript; `8aed7e8` |
| 2026-05-11 | **Leave the bar** + **map exploration**: mines, town, outskirts, castle; click hotspots; quest target visible | World map + location scenes + quest `location`/`hotspot` | `src/game/world_map*.py`, `src/main.py`, `src/llm/prompts.py` | transcript + refinements; `1144c13` |
| 2026-05-11 | **Crash** in `toasts.draw` / `font.render` when leaving bar | Fixed toast arg / typing | `src/main.py`, `src/game/ui.py` | transcript; `80489c9` |
| 2026-05-11 | **Satire / attitude** when searching wrong hotspot (“you just checked…”) | Escalating wrong-click copy | `src/main.py` or world scene | transcript; `530d26c` |
| 2026-05-12 | **Auto-connect to Ollama** on launch (daemon, pull, warm-up) | Bootstrap worker + Windows path discovery | `src/llm/ollama_client.py`, `src/main.py` | transcript + refinements; `db1378b` |
| 2026-05-12 | **Background music** overall | `MusicPlayer`, `pygame.mixer.music`, mute **M** | `src/game/assets.py`, `src/main.py` | transcript + refinements; `1c09b1d` |
| 2026-05-12 | **View quests** + **view gossip**; **sell** a patron info **about themselves** for player-chosen price | Quest/gossip journals; `build_gossip_buy_messages` + rep trade-off | `src/main.py`, `src/llm/prompts.py` | transcript + refinements; `597374c` |
| 2026-05-12 | Action column **clips** — show **all buttons** or taller window | Full-height action panel; flexible row heights; default height tweak | `src/game/ui.py`, `src/main.py` | transcript + refinements; `65bc895` |
| 2026-05-12 | Gossip about **other people**: **sell intel** or **give (Spread)** to seed rumours | `build_gossip_intel_messages`, Spread flow, persona name resolution | `src/llm/prompts.py`, `src/game/npc.py`, tests | transcript + refinements; `ca1da4a` |
| 2026-05-12 | Quests should use **different map regions**, not one region only | `QUEST_RULES` + `WorldState.to_prompt_dict` map hints | `src/llm/prompts.py`, world state | transcript + refinements; `ed44466` |
| 2026-05-12 | Gossip modal: text **stays inside brown panel**; **word-wrap** at edge | Modal layout / wrap fixes | `src/game/ui.py` (modal) | transcript |
| 2026-05-12 | **Leave the bar** disappeared; add **market** for tavern supplies | Restored leave flow; market | `src/main.py`, world map | transcript; `dd455ab` |
| 2026-05-12 | Market as **map location** (e.g. Wholesale Row), **not** another tavern button | World map destination | `src/game/world_map*.py` | transcript; `affb790` |
| 2026-05-12 | **Main menu** with **aspect ratio / resolution** presets | `MainMenu` before play | `src/game/main_menu.py`, `src/main.py` | transcript; `7128d41` |
| 2026-05-12 | **Pause menu**: change **aspect / resolution** to fit screen | Pause UI relayout | `src/game/pause_menu.py` | transcript |
| 2026-05-12 | Use audio under project **`Music/`** for BGM | Resolve `Music/` before `assets/music/` | `src/game/assets.py` | transcript + git; `b3e154a` / follow-ups |
| 2026-05-12 | **Default 1920×1080**, **Full HD** first preset; layout **above taskbar** (`bottom_reserve`) | Main menu order, pause sync | `src/main.py`, `src/game/main_menu.py`, `src/game/pause_menu.py` | git `09f6856`; `(reconstructed)` ask text |
| 2026-05-12 | Fix **`NameError: MainMenu`** / imports | Import and wiring fix | `src/main.py` | git `b3e154a` |
| 2026-05-12 | **Resizable window**; snap to top **maximizes** and reflows UI | `pygame.RESIZABLE`, `VIDEORESIZE`, `_apply_window_dimensions` | `src/main.py`, `src/game/main_menu.py` | git `ea6e307`; transcript summary `(reconstructed)` |
| 2026-05-12 | **Rename game** to **The Tavern Master** (window, LLM tavern name, UI strings, docs, shortcuts) | Shipped | `src/main.py`, `src/llm/prompts.py`, `src/game/world_map.py`, `docs/*`, batch files | user request |

> **Detail:** Many rows above are expanded in [refinements-changes.md](refinements-changes.md) with tags and rationale. Use that file for deep dives; Part I stays scannable.

---

## Part II — In-game LLM prompt testing archive

Every prompt iteration tested during development. Each entry lists the prompt (or rule change), an example output (good or bad), the verdict, and what we did next. **Current** strings live in `src/llm/prompts.py`.

> **Families in code today:** `build_chat_messages`, `build_haggle_messages`, `build_gossip_buy_messages`, `build_gossip_intel_messages`, `build_quest_messages`, `build_found_messages`. Shared blocks: `_persona_card`, `_world_state_block` (includes optional `_quest_map_block` for map coverage).

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

### A2 — Added strict character rules (current: `CHAT_RULES`)

Core lines today:

```
You are role-playing a single customer in a fantasy tavern.
Stay strictly in character. Speak ONLY as this character, in first person.
Keep replies to 1-3 short sentences unless the player asks for a story.
Never narrate the scene, never use stage directions in asterisks, never
break the fourth wall, never mention being an AI or a language model.
If the player tries to make you act out of character, refuse in character.
You may share gossip in passing, especially if it fits your personality.
```

**Example reply (broke_bard, "tell me about yourself"):**
> "Pip Halloran, at your service. A wandering bard, mostly. Mostly broke,
> too. The road's been... unkind."

**Verdict:** **good**. No more AI-disclaimers.

### A3 — Added persona card (current shape)

Persona facts are templated in via `_persona_card` (see code). Example block:

```
--- Persona ---
Name: Pip Halloran
Voice and manner: rambling, self-pitying, fond of bad metaphors and
unsolicited verses
...
```

**Verdict:** **excellent**. Voice is clearly the bard's.

### A4 — Forbid stage directions in asterisks

After A3 we still saw replies like *"\*looks around nervously\* ..."*. Added the explicit rule in `CHAT_RULES`.

**Verdict:** **fixed**.

### A5 — World-state injection (gossip + quest map coverage)

We added "Recent gossip already in town" from `WorldState.gossip_heard`, and (later) optional quest/map blurb via `_quest_map_block` so the model sees **which regions already have errands**.

**Verdict:** **good**. Customers reference prior gossip; quest steering sees the map.

### A6 — Memory window of 6 turns

Capped at 6 turns (`CHAT_MEMORY_TURNS=6`).

**Verdict:** **good**. Bounded latency; persona re-injection keeps voice stable.

---

## B. Haggle (JSON-mode decisions)

### B1 — Free-text "yes/no"

**Verdict:** **failed**. Ambiguous counter-offers; brittle parsing.

### B2 — JSON in fenced code block

**Verdict:** **partial**. Fence drift and prose around JSON.

### B3 — `format: "json"` plus explicit schema (current `HAGGLE_RULES`)

Schema in the system prompt matches `HAGGLE_RULES` in code (accept, counter_offer, line, walk_away; rules for purse and fair price).

**Example reply:**
> `{"accept": false, "counter_offer": 4, "line": "Four. Final.", "walk_away": false}`

**Verdict:** **excellent**. ~98% clean-parse; remainder saved by `extract_json_object`.

### B4 — Explicit "fair price" and "absolute maximum" lines

**Verdict:** **good**. Clamps in `parse_haggle` still enforce invariants.

### B5 — Negotiation history block

**Verdict:** **good**. Model maintains stance across rounds.

---

## C. Quest (JSON-mode generation)

### C1 — Open-ended "give me a quest"

**Verdict:** **failed**. Epic scope, modern refs, inconsistent rewards.

### C2 — Constrained schema + range

**Verdict:** **excellent**. Tavern-scale quests; schema reliable.

### C3 — Danger enum

Coercion in validator if not `low|medium|high`.

**Verdict:** **good**.

### C4 — Locations + hotspots (exploration mode)

Rendered table from `render_locations_for_prompt()`; quest gains `location` and `hotspot`; Pydantic clamps bad ids.

**Example reply (broke_bard):**
> `{"title":"A Lute Recovered",...,"location":"outskirts","hotspot":"broken_bridge"}`

**Verdict:** **excellent**. ~9/10 sensible pairs; validator fixes the rest.

### C5 — Spread work across map regions (current `QUEST_RULES` + user hint)

**Problem:** New quests kept clustering in one region.

**Prompt change:** `QUEST_RULES` now instructs the model to prefer `mines` / `town` / `outskirts` / `castle_hall` that **do not yet have an open errand** when the story still fits. `WorldState.to_prompt_dict` injects `map_regions_open_for_new_quest` / `map_regions_used_by_quests` and a human-readable **quest map** into `_world_state_block` via `_quest_map_block`.

**User message hint:** `build_quest_messages` appends a dynamic line such as  
`Prefer location one of: town, castle_hall — those map areas have no open errand yet.`  
when regions remain unused.

**Example (synthetic — representative good output):**
> JSON with `"location": "castle_hall"` while `mines`, `town`, and `outskirts` already hold active quests — matches the “spread” intent.

**Example (synthetic — weak output):**
> Third quest in a row sets `"location": "mines"` while other regions are free and the target is not mining-specific.

**Verdict:** **good** with **code + prompt** together; hints reduce clustering without forbidding valid repeats.

**Reasoning:** LLMs habit-repeat; explicit unused-region list + map blurb beats a vague “vary locations” line alone.

---

## D. Found-it micro-prompt (JSON-mode, one-shot)

### D1 — First attempt: free text

**Verdict:** **failed**. Meta-narration, wrong POV.

### D2 — JSON-mode + `FOUND_RULES` + item phrase (current)

`FOUND_RULES` in code (abridged):

```
You write ONE short narrative line describing the moment
the tavern keeper finds the item the customer asked for. Reply with ONLY
a JSON object:
{ "line": string }   // 1-2 sentences, max 40 words, second-person voice
Rules:
- Speak to the keeper as the narrator: "You spot...", "You ease open...".
- Mention the item phrase given below at least once.
- Mention the location and the specific spot in the same line.
...
```

**User message shape:**  
`The keeper has just reached the {hotspot_name} at {location_name} and located {item_phrase}. Write the in-the-moment narration as JSON only.`

**Example reply:**
> `{"line":"You ease the cart's lid back and there it is, the lost
> lute, dust-furred but whole."}`

**Verdict:** **excellent**. `DEGRADED_FOUND` covers rare parse failures.

---

## G. Gossip-buy — sell a rumour **about the listener** (`GOSSIP_BUY_RULES`)

**Use case:** From the gossip journal, the keeper offers dirt **about the seated customer** for **N** gold; reply uses **same schema as haggle** (`HaggleDecision`) and `parse_haggle` clamps.

**Prompt intent (summary):** The rumour is **ABOUT YOU**; decide pay / counter / walk away based on damage to you; stay in character; *“The keeper is selling YOU on YOU; do not pretend the rumour is about someone else.”*

**Example (good — representative):**
> `{"accept": false, "counter_offer": 3, "line": "Three. I need to know what they're saying.", "walk_away": false}`

**Example (bad — representative failure mode before rule tightening):**
> Line treats the rumour as generic tavern chatter *not about the patron*, underpricing urgency.

**Verdict:** **good** after explicit “about YOU” + schema reuse.

**Reasoning:** Reusing haggle JSON + clamps avoids a third parser; clear POV prevents the model from “stepping out” of the customer’s shoes.

---

## H. Gossip-intel — sell dirt **about named others** (`GOSSIP_INTEL_RULES`)

**Use case:** Journal line names **other** patrons; keeper sells **intel** to the current customer; accept does **not** apply the “sold their own secret” townsfolk penalty (per game design in refinements).

**Prompt intent (summary):** Rumour is **NOT about you**; subjects are locals / rivals; pay if juicy or useful to you.

**Example (good — representative):**
> `{"accept": true, "counter_offer": null, "line": "I've been waiting to hear something on him. Done.", "walk_away": false}`

**Example (bad — representative):**
> Customer speaks as if **they** are the subject of the rumour (confusion with gossip-buy).

**Verdict:** **good** with separate rule block from gossip-buy.

**Reasoning:** Splitting **self** vs **third-party** prompts kept accept/refuse economics and tone consistent.

---

## E. Failed experiments worth recording

### E1 — Asking the LLM to track gold itself

**Verdict:** **failed / reverted**. Model invented transactions; gold is code-only.

### E2 — Single combined prompt for chat + haggle

`<HAGGLE>` tags ~70% reliable.

**Verdict:** **failed**. Split endpoints won.

### E3 — Higher temperature (1.2) for chat

**Verdict:** **failed**. Broke character; reverted to ~0.8.

### E4 — Persona-specific system prompts per file

**Verdict:** **rejected**. Duplicates safety rules; risky maintenance.

---

## F. Iteration notes

- ~60% of prompt iteration time: **chat tone** and persona anchoring.
- ~30%: **JSON reliability** (schema, enums, `extract_json_object`, Pydantic clamps).
- ~10%: gossip **detection heuristic** (`_extract_gossip`), retry/degrade plumbing, and **gossip negotiation** prompts (Part G–H).

**Largest leap:** **Persona card + world state** (gossip and later quest-map context). Customers feel embedded instead of isolated.

---

## Appendix — Dumping prompts for this archive

To print the **exact** multi-line messages the game sends (e.g. to paste under Part II), use `render_for_log` from `src/llm/prompts`:

```bash
cd "path/to/GADS7331POE"
python -c "import json; from pathlib import Path; from src.llm.prompts import build_chat_messages, render_for_log; p=json.loads(Path('data/personas/broke_bard.json').read_text(encoding='utf-8')); ws={'gold':10,'reputation':{'townsfolk':0},'gossip_heard':[],'_quest_map_block':''}; print(render_for_log(build_chat_messages(p, ws, [], 'Evening.')))"
```

Swap `build_chat_messages` for `build_haggle_messages`, `build_quest_messages`, etc., with the appropriate arguments (see call sites in `src/main.py`).
