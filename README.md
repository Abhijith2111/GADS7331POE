# The Tavern Master

A small Python/Pygame fantasy tavern simulator where every customer's
dialogue, haggling, gossip, and quest offer is generated live by a
**local Large Language Model** through [Ollama](https://ollama.com/).

The player runs the bar. Customers walk in one at a time, each with a
hand-authored persona (a paranoid wizard, a broke bard, a smug noble, a
gruff dwarf, a mysterious traveller). You can chat with them, haggle on
prices for ales and rooms, listen for gossip that gets remembered for
later customers, and accept short fetch-quests. The LLM does not just
flavour-text the scene — it makes the gameplay decisions the
shopkeeper genre depends on (does this customer accept your price?).

> **Module:** GADS7331POE
> **Built with:** Python 3.11+, Pygame 2.6, Ollama, llama3.2:3b (default).

---

## Easy launch (Windows)

1. Install **Python 3.11+** and **Ollama** once from
   <https://ollama.com/download> (~2 GB model downloads on first run).
2. Double-click **[setup.bat](setup.bat)** once.
3. Double-click **[run_game.bat](run_game.bat)** to play.

The **main menu** lets you pick one of **three save slots**, adjust
**music volume**, start a **New Game** or **Continue**, and choose
window size. Saves and settings live under `data/saves/` and
`data/settings.json`. The game auto-starts Ollama if installed.

Optional extras:

- **[run_demo.bat](run_demo.bat)** — scripted demo session (fixed seed + prompt logs).
- **[make_desktop_shortcut.bat](make_desktop_shortcut.bat)** — Desktop shortcut to `run_game.bat`.

The Quick Start below still works for any platform or for users who
prefer the command line.

---

## Quick start

1. **Install Python 3.11 or newer** — <https://www.python.org/downloads/windows/>.
2. **Install Ollama** — <https://ollama.com/download>. Start the daemon
   (`ollama serve`) or simply leave the tray app running.
3. **Pull the default model:**
   ```powershell
   ollama pull llama3.2:3b
   ```
4. **Clone this repo and install dependencies:**
   ```powershell
   git clone <repo-url> GADS7331POE
   cd GADS7331POE
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
5. **Run:**
   ```powershell
   python -m src.main
   ```

Full step-by-step (including troubleshooting) is in
[docs/setup.md](docs/setup.md).

---

## Demo / video-evidence mode

For reproducible footage:

```powershell
python -m src.main --demo --persona broke_bard --turns 4 --seed 1234
```

This:

- spawns a fixed persona (`broke_bard`),
- runs four scripted player inputs (greeting, gossip prompt, haggle, quest),
- uses a fixed Ollama seed so the same prompts produce stable replies,
- writes `prompt_log_<timestamp>.jsonl` and `demo_log_<timestamp>.jsonl`
  to the working directory so every prompt and reply is auditable on tape.

---

## Controls

- Type into the input bar at the bottom and press **Enter** to talk.
- Slash-commands while talking:
  - `/items` — list the bar's stock.
  - `/sell <item_id> <price>` — offer to sell at a price (starts a haggle).
  - `/quest` — ask the customer if they have any work.
  - `/next` — send this customer away, spawn the next one.
  - `/save` — persist the active save slot.
  - `/help` — open the in-game help guide.
- **F1** help, **F2** settings (model picker / temperature / regenerate
  last reply / banner toggle), **F5** next customer, **T** hide the AI
  notice, **M** mute/unmute background music, **Esc** pause menu.

### Start-up flow

- The **main menu** is laid out top-to-bottom like a normal game: choose a
  **save slot**, then **New Game / Continue**, then **music volume** and
  **resolution** (a click-to-cycle window-size button), then **Help**, then
  **Quit**. The **Help** button (or **F1**) opens an illustrated guide that
  explains the screen layout and what every action button does.
- After you pick a slot, a short **briefing screen** describes what you'll
  be doing before play begins (with its own **Begin / Help / Back** buttons).

### Action panel (grouped & colour-coded)

The buttons on the right of the bar are **grouped by purpose** and tinted
so they don't blend together. Buttons with a small **▶ arrow** expand into
a sub-list with a **◀ Back** button:

- **Trade ▶** (amber) — *Show stock*, *Sell item…*
- **Quests ▶** (blue) — *Ask for work*, *View quests*
- **View gossip** (violet) — standalone
- **Next customer** (teal) / **Leave the bar** (green) — standalone
- **Menu ▶** (slate) — *Save game*, *Help*, *Quit*

### Pause menu (Esc)

Press **Esc** to pause. Ordered like a normal game's pause screen, it lets you
**Resume**, adjust **music volume** (slider or ←/→), change the **window size**
(Apply), return to the **Main Menu**, or **Quit**. Choosing Main Menu or Quit
first asks whether you want to **save** so progress is never lost by accident.
You can also quit straight from the in-game **Menu ▶ Quit** button, which opens
the same save-or-discard prompt.

### Background music

A calm ambient pad plays on a loop in the background, generated
procedurally on first launch so there's nothing to ship and no
copyright noise. Press **M** to mute it. If you want a real track
instead, drop any `.ogg`, `.wav`, or `.mp3` file into `assets/music/`
and the game will use it on next launch (alphabetical first wins).

### Journal: quests and gossip

Two action-panel buttons surface what the world has remembered for you:

- **View quests** — a modal with every active quest (title, summary,
  the location and hotspot where the item hides, reward, danger) and a
  list of recently completed ones.
- **View gossip** — a modal with every rumour you've overheard while
  chatting. Lines are scanned for **full names from `data/personas/`**
  (substring match) or long first names (whole-word match). When
  someone is at the bar:
  - **Sell re: _Patron_** — they'll pay (LLM haggle) to hear dirt
    *about themselves*; gold in, **-1 townsfolk**, rumour removed.
  - **Sell intel** — if the line names *other* regulars, you haggle a
    price to sell that third-party gossip. Gold in, **no rep penalty**,
    rumour removed on a deal.
  - **Spread** — hand them the same third-party rumour **for free**:
    the original line is removed, a new derivative rumour is added so
    it propagates through the town pool, and you gain **+1 townsfolk**.

### Leaving the bar (quest exploration)

When you accept a quest, **"Leave the bar"** appears in the action panel.
That opens a world map of four hand-authored locations — *The Old Mines,
Town Square, The Outskirts,* and the *Castle Hall* — each with four
search hotspots. The location holding your quest target glows.

Click a location card to walk into it. Pulsing dots are searchable
hotspots: click the right one and the LLM writes a single short "you
found it" line, the reward is deposited, and the game whisks you back
to the bar. Wrong clicks just print "Nothing useful here." and cost
nothing.

The location *and* the hotspot are chosen by the LLM at quest-generation
time (validated/clamped server-side so a wandering model can never
make a quest unreachable). All the location and hotspot art is
procedural — no external assets needed.

---

## Project structure

```
GADS7331POE/
├─ README.md                 ← you are here
├─ requirements.txt
├─ docs/                     ← all required documentation
│  ├─ high-concept.md
│  ├─ ollama-plan.md
│  ├─ setup.md
│  ├─ refinements-changes.md
│  ├─ prompts-used.md
│  └─ llm-integration-report.md
├─ src/
│  ├─ main.py
│  ├─ game/                  ← Pygame layer
│  │  ├─ main_menu.py        ← save-slot launcher (+ Help button)
│  │  ├─ info_screens.py     ← briefing + illustrated help guide
│  │  ├─ pause_menu.py       ← Esc pause (resume / menu / quit + save prompt)
│  │  ├─ ui.py               ← widgets, colour-coded action panel
│  │  └─ ...                 ← scene, world map, npc, settings, save slots
│  └─ llm/                   ← Ollama client, prompts, parsers
├─ data/
│  ├─ personas/              ← 5x persona JSONs (modifiable)
│  ├─ items.json
│  └─ saves/                 ← three save slots + settings.json
├─ assets/
│  ├─ sprites/               ← optional, falls back to procedural art
│  ├─ fonts/                 ← optional, falls back to system serif
│  └─ sfx/                   ← optional door/coin/quest WAVs
└─ tests/
   ├─ test_parsers.py
   ├─ test_paths.py
   ├─ test_rumour_memory.py
   ├─ test_save_slots.py
   └─ test_settings.py
```

[`docs/prompts-used.md`](docs/prompts-used.md) is the **combined archive**: Part I logs what was asked for in Cursor (features and tooling), Part II logs Ollama prompt iterations; the appendix shows how to dump current prompts with `render_for_log`.

Run the test suite with `pytest -q`.

---

## Dependencies

- `pygame-ce>=2.5.0` (drop-in replacement for `pygame` with current pre-built wheels)
- `ollama>=0.3.3` (Python client; we also use `requests` directly)
- `requests>=2.32.0`
- `pydantic>=2.8.0`
- `pytest>=8.3.0`

The LLM itself runs **locally** through Ollama. No data leaves the
machine; no API key, no network calls beyond `localhost:11434`.

---

## Credits and disclosures

- **LLM:** [Ollama](https://ollama.com/) running
  [Meta Llama 3.2 (3B Instruct)](https://www.llama.com/llama3_2/) by
  default. Llama is released under the
  [Llama 3.2 Community License](https://www.llama.com/llama3_2/license/).
  Alternative compatible models: Qwen 2.5, Gemma 2, Mistral 7B —
  swap with `--model <tag>`.
- **Engine:** [Pygame](https://www.pygame.org/) (LGPL).
- **Validation:** [Pydantic](https://docs.pydantic.dev/) (MIT).
- **Sprites & art:** procedurally generated at runtime by `src/game/assets.py`.
  Players can drop their own PNGs into `assets/sprites/` (named after the
  persona's `sprite` field).
- **AI tools used to build the project itself:** Cursor (Anthropic Claude)
  was used as a coding assistant during development, alongside the same
  local Llama model used at runtime for prompt iteration. Specific
  decisions and refinements made with AI help are logged in
  [docs/refinements-changes.md](docs/refinements-changes.md).

### Player awareness

A small banner across the top of the screen reminds the player that NPC
dialogue is generated by a local LLM. It can be toggled with **T** but
is **on by default**, in line with the ethical-disclosure section of
[docs/llm-integration-report.md](docs/llm-integration-report.md).

---

## License

This student project is provided for academic review. The Llama model
and Pygame retain their respective licences as linked above.
