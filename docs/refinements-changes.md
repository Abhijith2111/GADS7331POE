# Refinements and Changes

A running log of scope changes and AI-assisted decisions made during
development. Newest entry at the top.

---

## 2026-05-11 — Switched dependency from `pygame` to `pygame-ce` (build fix)

**Tag:** `dependencies`, `windows`
**Source:** install failure on Windows during step 3d of the setup guide.

- First-time `pip install -r requirements.txt` failed on a clean Windows
  machine while building `pygame` from source:
  `ModuleNotFoundError: No module named 'distutils.msvccompiler'`.
- Root cause: pip could not find a pre-built `pygame` wheel for the
  installed Python version, so it tried to compile from source. The
  source build imports `distutils.msvccompiler`, which was removed from
  Python's stdlib in 3.12 and from `setuptools._distutils` in
  setuptools 74+.
- Fix: changed the pinned dependency to **`pygame-ce>=2.5.0`** — the
  community-maintained fork ships up-to-date Windows wheels for current
  Python versions and is a drop-in replacement (`import pygame` still
  works unchanged in our code).
- Updated `README.md` and `docs/setup.md` to reflect the new pin and
  added a troubleshooting row for the original error message.

> **How to read this file:** each entry is dated, tagged with the area
> it touched, and notes whether the decision was AI-assisted (Cursor /
> Claude as a coding assistant, or the local Llama model used for
> prompt iteration) or made by hand.

---

## 2026-05-10 — Initial planning round (AI-assisted)

**Tag:** `scope`
**Source:** plan-mode brainstorm with Cursor, then user picked the
"fantasy shopkeeper / tavern sim" option.

- Considered five concept directions (detective, dungeon master,
  shopkeeper, escape room, interactive fiction). Picked the tavern sim
  because it lets the LLM make *gameplay* decisions (haggling), not
  just flavour text — a more substantive integration showcase.
- Picked Python + Pygame over Unity / Godot because Ollama integration
  is tighter (no boilerplate around streaming JSON) and the schedule
  needs more time on documentation than on engine glue.

## 2026-05-10 — Default model: 3B over 7B (AI-assisted)

**Tag:** `model`

- Initial pull was `llama3.1:8b` to maximise quality. First-token
  latency on the test laptop (no GPU, 16 GB RAM) was 4.5 – 6 s, which
  felt slow during streaming chat.
- Switched to `llama3.2:3b`. First-token latency dropped to ~1.5 s
  with the daemon warm. Quality was sufficient for short, single-
  customer dialogue. Documented `llama3.1:8b` as an opt-in upgrade for
  GPU users instead of the default.

## 2026-05-10 — Persona re-injection (AI-assisted)

**Tag:** `prompt`

- During the first prototype playtest, customers visibly drifted out
  of voice after about six turns — the bard would start sounding like
  the noble. Adding the full persona card to the system prompt every
  turn (rather than just the first) fixed the drift without harming
  latency, because the persona block is short.
- Capped chat memory at the last 6 turns (`CHAT_MEMORY_TURNS` in
  `src/llm/prompts.py`). Older turns are truncated; the system prompt
  remains anchored.

## 2026-05-10 — Haggle clamps in code, not in prompt (manual)

**Tag:** `prompt`, `safety`

- Initially we tried to make the prompt enforce the budget (`"never
  accept above your coin purse"`). The model still occasionally
  accepted offers above the persona's `budget_gold`.
- Moved the enforcement to `parse_haggle` in `src/llm/parsers.py`.
  The model is still asked nicely in the prompt, but a hard clamp
  guarantees the gameplay invariant. This is the recommended pattern
  from the Ollama docs: "trust but verify".

## 2026-05-10 — JSON-mode for decisions, free chat for dialogue (AI-assisted)

**Tag:** `prompt`

- A first version put haggle decisions inside the chat reply ("OK, I
  accept" / "No, how about 5 gold?"). Parsing those turned into a
  brittle regex jungle.
- Split into two endpoints: chat (free-form, streamed) and JSON-mode
  (one structured object, parsed with Pydantic). This is the single
  biggest reliability win of the project.

## 2026-05-10 — Robust JSON extractor (manual)

**Tag:** `parsing`

- Even with `format: "json"`, the smaller models occasionally emit
  a leading "Sure, here you go:" before the object. Added
  `extract_json_object` to scan for the first `{...}` block as a fallback.
  Test cases cover both paths.

## 2026-05-10 — Gossip detection: heuristic, not LLM-driven (manual)

**Tag:** `feature`, `performance`

- We considered running a second LLM call after each chat reply to
  classify "is this gossip?". That would double the latency budget on
  every chat turn for a feature that only needs to be roughly right.
- Replaced with a tiny string-trigger heuristic in `_extract_gossip`
  (looks for "rumour", "they say", "i heard", etc.). False positives
  are fine because gossip is dedupe'd and capped at 20 entries.

## 2026-05-10 — Banner on by default (ethics)

**Tag:** `ethics`

- Discussed whether the AI-disclosure banner should be off by default
  with a setting to enable it. Decided **on by default**: the player
  must see at least once that NPC dialogue is machine-generated. They
  can hide it with `T` after that. This is documented in the integration
  report's ethics section.

## 2026-05-10 — Procedural fallback art (scope)

**Tag:** `scope`

- Bundling sprite art has copyright/attribution overhead and risks
  shipping a build that fails the marker's clean-clone test. Decided
  to ship **no** image assets and to draw stylised silhouettes from
  each persona's `color_accent` value at runtime. If a real PNG exists
  at `assets/sprites/<filename>` it is preferred — so modders can swap
  in real art without touching code.

## 2026-05-10 — `--demo` mode for video evidence (scope)

**Tag:** `feature`

- Added a `--demo` flag that runs a fixed sequence of player inputs
  with a fixed model seed and dumps the full prompt/response log to
  `prompt_log_*.jsonl`. Lets the marker reproduce a specific demo
  scene from the video without waiting for the live model to behave.

## (Add new entries here as the project evolves)
