# The Wandering Goblet

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

If you are on Windows and just want to play, no PowerShell required:

1. Install **Python 3.11+** from <https://www.python.org/downloads/windows/>
   (tick *"Add python.exe to PATH"* during install) and **Ollama** from
   <https://ollama.com/download>.
2. Double-click **[setup.bat](setup.bat)** once. It creates the virtual
   environment, installs dependencies, and pulls the default Ollama
   model.
3. Double-click **[run_game.bat](run_game.bat)** any time you want to
   play.

Optional extras:

- **[run_demo.bat](run_demo.bat)** — double-click to launch the scripted
  demo session (fixed seed + prompt logs) used for video evidence.
- **[make_desktop_shortcut.bat](make_desktop_shortcut.bat)** — run once
  to drop a "Wandering Goblet" shortcut on your Desktop pointing at
  `run_game.bat`.

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
  - `/save` — persist `data/savegame.json`.
  - `/help` — in-game cheat-sheet.
- **F1** help, **F2** settings (model picker / temperature / regenerate
  last reply / banner toggle), **F5** next customer, **T** hide the AI
  notice, **Esc** quit.

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
│  └─ llm/                   ← Ollama client, prompts, parsers
├─ data/
│  ├─ personas/              ← 5x persona JSONs (modifiable)
│  ├─ items.json
│  └─ savegame.json
├─ assets/
│  ├─ sprites/               ← optional, falls back to procedural art
│  ├─ fonts/                 ← optional, falls back to system serif
│  └─ sfx/                   ← optional door/coin/quest WAVs
└─ tests/
   └─ test_parsers.py
```

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
