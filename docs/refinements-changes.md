# Refinements and Changes

A running log of scope changes and AI-assisted decisions made during
development. Newest entry at the top.

---

## 2026-05-12 — Added procedural background music

**Tag:** `feature`, `audio`
**Source:** user request ("could add some background music").

- Until now the only audio surface was the optional SFX layer (door /
  coin / quest WAVs, which weren't shipped either). The tavern was
  silent on a clean clone.
- Added a `MusicPlayer` in `src/game/assets.py` that drives the
  `pygame.mixer.music` channel. It looks for a track in
  `assets/music/` first (any `.ogg`/`.wav`/`.mp3`, alphabetical first
  wins) so a player can drop in a real piece of music without touching
  code. If nothing is there, it generates a 16-second warm-pad
  ambience procedurally (`array` + `wave`, no numpy dependency) and
  streams it on loop. The first/last 0.6 s cross-fade to silence so
  the loop seams are inaudible.
- Wiring: `Game.__init__` starts the music on a background thread so
  generation doesn't block the window from appearing. `--demo` mode
  skips music entirely (captured video should hear the dialogue
  itself, not background drone). **M** toggles mute. `dispose()` is
  called on exit, which stops + unloads the track and deletes the
  temp WAV.
- Default volume is intentionally low (32%) so the music sits *under*
  the dialogue text rendering rhythm rather than competing with it.

---

## 2026-05-12 — Game now auto-starts Ollama and auto-pulls the model

**Tag:** `dx`, `setup`, `windows`
**Source:** user feedback ("make it so launching the game just connects
to Ollama with no connection problems"). AI-assisted (Cursor / Claude).

- Until now, launching the game on a fresh machine could fail in three
  unrelated ways: (a) Ollama daemon not started, (b) configured model
  not pulled, (c) cold model meaning the first chat felt slow. The
  player had to debug all three from a single "Ollama not reachable"
  toast.
- Added a bootstrap worker that runs in the background on launch and
  does the right thing for each case:
  1. **Daemon discovery** (`find_ollama_executable` in
     `src/llm/ollama_client.py`) walks PATH and the two default Windows
     install paths (`%LOCALAPPDATA%\Programs\Ollama\ollama.exe`,
     `%ProgramFiles%\Ollama\ollama.exe`). The Ollama installer doesn't
     always update PATH for the current shell session, so PATH alone
     was unreliable.
  2. **Auto-launch** the daemon via `ollama serve` as a detached
     background process (no console window on Windows, survives the
     game exit so other Ollama tooling keeps working). Polls until
     reachable, up to 25 seconds.
  3. **Auto-pull** the configured model via the streaming
     `POST /api/pull` endpoint. The UI shows progress toasts
     ("Pulling llama3.2:3b: downloading 30%"), throttled to ~3/sec.
  4. **Warm up** the model with a 1-token call so the first real chat
     hits a hot model and returns its first token in ~1 s instead of
     ~5 s.
- All status messages are pushed via the existing event queue so the
  worker never touches pygame surfaces directly. UI stays responsive
  the entire time the daemon is starting / the model is downloading.
- `setup.bat` was reworded: the up-front `ollama pull` is now clearly
  optional ("safe to skip — the game can also pull it on first
  launch"). This lets new players double-click and play even if they
  cancel the slow first-time pull.

---

## 2026-05-11 — Added quest exploration mode (AI-assisted)

**Tag:** `feature`, `scope`, `prompt`
**Source:** plan in `docs/quest_exploration_mode_*.plan.md`, built out with
Cursor / Claude in agent mode.

- Until this point the quest loop ended at "customer offers a quest,
  reward goes into a pending bucket". The marker had no visible reason
  to keep playing once they'd seen the haggle and quest prompts fire.
- Added a second mode: once at least one quest is active, the action
  panel shows **"Leave the bar"**. That opens a world map of four
  hand-authored locations (mines, town, outskirts, castle hall). Each
  location has four search hotspots. The location with the quest's
  target glows; the others are dimmed but still clickable for free
  exploration.
- In a location, clicking the right hotspot fires one short JSON-mode
  prompt (`build_found_messages` in `prompts.py`) for an in-character
  "you found it" line; the reward is deposited, reputation ticks, and
  the player is whisked back to the bar after a 1.6 s celebration.
  Wrong clicks print a fixed "Nothing useful here." note with no LLM
  call.
- **MVP scope rationale.** Locations and hotspots are hand-authored,
  not LLM-generated, because (a) the LLM-driven *placement* is the
  interesting decision the model already makes well, and (b) tiling
  the player's world from a model output adds a much bigger reliability
  problem (mis-named ids, locations the player can't actually visit)
  for very little gameplay payoff inside the brief's time budget.
  Adding a fifth location later is one dict entry in
  `src/game/world_map.py`.
- **Schema change.** `Quest` Pydantic model gained `location` and
  `hotspot` fields. Both are clamped server-side (unknown location →
  `outskirts`; hotspot from the wrong location → that location's first
  hotspot) so a wandering model can never make a quest unreachable.
  `WorldState.load` was taught to fill defaults on older saves missing
  these fields, so existing players keep their progress.
- **Art is procedural.** Each location has a 4-colour palette and a
  small painter function in `world_map.py` (mines = jagged stone +
  torch glow, town = silhouette buildings, outskirts = trees + path,
  castle hall = columns + banner + throne). Consistent with the rest
  of the game's "no shipped image assets" policy.
- Tests added in `tests/test_parsers.py`: `TestParseQuestLocation`
  covers the clamping/fallback behaviour, `TestExtractItemPhrase`
  covers the regex used to feed the found-it prompt.
- Docs updated: `README.md` got a "Leaving the bar" subsection,
  `docs/high-concept.md` extended its "what's code / what's LLM"
  table, `docs/ollama-plan.md` added the found-it row + section 4.4,
  and `docs/prompts-used.md` added entries C4 and D1–D2.

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
