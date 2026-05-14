# Setup Guide

Complete instructions for getting **The Tavern Master** running on a
clean Windows machine. Linux and macOS notes are at the bottom.

> **In a hurry?** Skip to [section 8 — Easy launch with .bat files](#8-easy-launch-on-windows-no-powershell)
> for the double-click route. The sections below cover the manual
> PowerShell flow that section 8 wraps for you.

---

## 1. System requirements

| Component | Minimum                       | Recommended                  |
| --------- | ----------------------------- | ---------------------------- |
| OS        | Windows 10 (64-bit)           | Windows 11                   |
| CPU       | 4-core x86_64                 | 8-core x86_64                |
| RAM       | 8 GB                          | 16 GB or more                |
| Disk      | 4 GB free (for Ollama model)  | 10 GB free                   |
| GPU       | None required (CPU works)     | NVIDIA / Apple Silicon       |
| Python    | 3.11 or newer                 | 3.12                         |
| Ollama    | 0.3 or newer                  | latest                       |

The game has been tested on:

- Windows 11, AMD Ryzen 7, 16 GB RAM, no discrete GPU. Default
  `llama3.2:3b` runs at roughly 30 tokens/s on this configuration with
  first-token latency around 1.5 s once the daemon has warmed up.

---

## 2. Install Ollama

1. Download the Windows installer from <https://ollama.com/download/windows>.
2. Run the installer with default options. It registers an Ollama
   service that auto-starts on login and listens on `localhost:11434`.
3. Verify the daemon is up by opening PowerShell and running:

   ```powershell
   curl http://localhost:11434
   # expected: "Ollama is running"
   ```

   If you see a connection error, open a new PowerShell window and
   start the daemon manually:

   ```powershell
   ollama serve
   ```

4. Pull the default model. This downloads ~2 GB the first time:

   ```powershell
   ollama pull llama3.2:3b
   ```

5. Confirm the model is locally available:

   ```powershell
   ollama list
   # NAME                 ID              SIZE     MODIFIED
   # llama3.2:3b          ...             2.0 GB   ...
   ```

Optional: pull a fallback or upgrade model.

```powershell
ollama pull qwen2.5:3b           # similar size, slightly cleaner JSON
ollama pull gemma2:2b            # smaller, for low-RAM machines
ollama pull llama3.1:8b          # larger, if you have a GPU
```

---

## 3. Install Python

1. Download Python 3.11 or 3.12 from
   <https://www.python.org/downloads/windows/>.
2. **Important:** in the installer, tick *"Add python.exe to PATH"*
   before clicking *Install Now*.
3. Confirm the install:

   ```powershell
   python --version
   # expected: Python 3.11.x or 3.12.x
   ```

If `python` is not recognised but you see "Python was not found; run
without arguments to install from the Microsoft Store", uninstall the
Microsoft Store stub via *Settings → Apps → Advanced app settings →
App execution aliases* (turn both Python entries off) and reinstall
from python.org.

---

## 4. Get the project and install dependencies

```powershell
git clone <repo-url> GADS7331POE
cd GADS7331POE
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If `Activate.ps1` is blocked by the execution policy, run PowerShell
as the current user once with:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

`requirements.txt` pulls:

- `pygame-ce>=2.5.0` (drop-in replacement for `pygame` with up-to-date wheels)
- `ollama>=0.3.3`
- `requests>=2.32.0`
- `pydantic>=2.8.0`
- `pytest>=8.3.0`

> **Why `pygame-ce` instead of `pygame`?** On recent Python versions
> (3.12+) the original `pygame` source build fails on Windows because it
> still imports `distutils.msvccompiler`, which was removed from the
> stdlib. `pygame-ce` ships current pre-built wheels and is API-compatible
> (`import pygame` still works in code).

---

## 5. Run the game

```powershell
python -m src.main
```

The game window should open on the tavern scene. The first customer
walks up to the counter; type a greeting and press **Enter**. The first
LLM call takes a moment longer than subsequent ones because Ollama is
loading the model into memory.

### Common run-time flags

```powershell
python -m src.main --model qwen2.5:3b   # use a different local model
python -m src.main --seed 42            # reproducible model output
python -m src.main --demo               # scripted demo + prompt log
python -m src.main --demo --persona paranoid_wizard --turns 4
```

### Run the test suite

```powershell
pytest -q
```

---

## 6. Troubleshooting

| Symptom                                                            | Fix                                                                                                                                     |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| Game window opens but a red toast says *"Ollama not reachable"*   | Run `ollama serve` in another terminal, or restart the Ollama tray app.                                                                 |
| `model 'llama3.2:3b' not found`                                    | `ollama pull llama3.2:3b`. Then either restart the game or use F2 → Cycle model to refresh the model list.                              |
| Replies arrive but no text appears in the dialogue box             | Check that the input bar is in focus. Click on the bar and try again.                                                                  |
| First reply takes 8+ seconds                                       | The daemon is loading the model into memory. Subsequent replies use the cache. If it stays slow, try `--model gemma2:2b`.               |
| `pygame.error: video system not initialized` when running tests    | Tests do not need pygame; we only import `parsers`. If you see this, run `pytest -q tests/test_parsers.py` explicitly.                  |
| `Failed to build 'pygame' ... ModuleNotFoundError: No module named 'distutils.msvccompiler'` | Old pin on `pygame` instead of `pygame-ce`. Pull the latest `requirements.txt` (`git pull`), then re-run `pip install -r requirements.txt`. |
| `Activate.ps1 cannot be loaded`                                    | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, then re-run.                                                     |
| Streaming reply hangs forever                                      | Check the Ollama tray app — sometimes a stuck request blocks the queue. Restart Ollama (right-click tray → Quit, then re-launch).       |
| Game loads but text looks like boxes                               | The bundled font fell back to a system one that lacks glyphs. Drop a TTF into `assets/fonts/main.ttf`.                                  |

---

## 7. Linux / macOS notes

The game is platform-portable; only the install commands change.

```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.main
```

```bash
# macOS (Apple Silicon strongly recommended)
brew install ollama
brew services start ollama
ollama pull llama3.2:3b
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.main
```

On Apple Silicon the default model runs at native GPU speed and
first-token latency is typically below 700 ms.

---

## 8. Easy launch on Windows (no PowerShell)

For Windows users who would rather not touch a terminal, the project
ships four batch files in the repo root that wrap the same commands as
the manual sections above.

| File                              | What it does                                                              | When to run     |
| --------------------------------- | ------------------------------------------------------------------------- | --------------- |
| **setup.bat**                     | Creates `.venv`, installs `requirements.txt`, pulls `llama3.2:3b`        | Once after clone |
| **run_game.bat**                  | Activates the venv and launches the game                                  | Every play session |
| **run_demo.bat**                  | Scripted demo: `--demo --persona broke_bard --turns 4 --seed 1234`        | For video evidence |
| **make_desktop_shortcut.bat**     | Creates a "The Tavern Master" shortcut on your Desktop                     | Optional, once   |

### Step-by-step

1. Install **Python 3.11+** from <https://www.python.org/downloads/windows/>
   (tick *"Add python.exe to PATH"* during install) and **Ollama** from
   <https://ollama.com/download>. These two installers cannot be wrapped
   in a `.bat` because they need administrator UI prompts.
2. Open the project folder in Windows Explorer.
3. Double-click **`setup.bat`**. A console window appears, prints its
   progress, and pauses on `Setup complete.` when done. Close it.
4. Double-click **`run_game.bat`**. The game window opens.
5. (Optional) double-click **`make_desktop_shortcut.bat`** once to put a
   one-click launcher on your Desktop.

### Passing extra flags through

Both `run_game.bat` and `run_demo.bat` forward extra arguments to
`python -m src.main`. So you can still customise from the command line
or by editing the file:

```bat
run_game.bat --model qwen2.5:3b
run_demo.bat --persona paranoid_wizard
```

### When to fall back to PowerShell

If something in `setup.bat` fails (most common cause: Python or pip
errors), the script pauses with the error visible. You can then re-run
the same steps manually using the PowerShell instructions in section 4
above to get a clearer view of what went wrong.
