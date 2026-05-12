"""Ollama HTTP client wrappers.

Two surfaces are exposed to the rest of the game:

- ``chat_stream`` for free-form, character-by-character NPC dialogue.
- ``json_call`` for structured decisions (haggling, quest generation) where
  the model is constrained to emit valid JSON via Ollama's ``format`` field.

The module deliberately depends only on ``requests`` so the game keeps
working on machines without the optional ``ollama`` Python package, but it
will prefer the package when present for nicer error messages.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

import requests

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2:3b"

# Conservative timeouts. The streaming endpoint can block while the model
# warms up on first call; the request library treats this as a single read,
# so a generous read timeout avoids spurious failures.
CONNECT_TIMEOUT_S = 5
READ_TIMEOUT_S = 120


class OllamaError(RuntimeError):
    """Raised when Ollama is unreachable or returns a malformed payload."""


# ---------------------------------------------------------------------------
# Daemon discovery + auto-launch
# ---------------------------------------------------------------------------
def find_ollama_executable() -> str | None:
    """Return a path to the ``ollama`` binary, or None if it isn't installed.

    Looks on PATH first (covers macOS, Linux, and Windows installs that
    ticked "Add to PATH"). On Windows we also probe the two default
    install locations because the Ollama installer does *not* always
    update PATH for the current shell session.
    """
    found = shutil.which("ollama")
    if found:
        return found
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Ollama" / "ollama.exe",
        ]
        for p in candidates:
            if p.is_file():
                return str(p)
    return None


def _spawn_daemon(executable: str) -> bool:
    """Spawn ``ollama serve`` as a detached background process.

    Returns True if the subprocess was launched (the daemon may still be
    starting up after this returns). On Windows the console window is
    suppressed and the process is put into its own group so closing the
    game won't kill the daemon.
    """
    kwargs: dict[str, Any] = dict(
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    if os.name == "nt":
        flags = 0
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen([executable, "serve"], **kwargs)
        return True
    except OSError:
        return False


@dataclass
class OllamaConfig:
    """Runtime configuration for a single Ollama session.

    Stored on the game instance so the settings menu can mutate it without
    rebuilding clients.
    """

    host: str = DEFAULT_HOST
    model: str = DEFAULT_MODEL
    chat_temperature: float = 0.8
    json_temperature: float = 0.2
    seed: int | None = None
    keep_alive: str = "10m"
    extra_options: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptLogEntry:
    """One prompt/response pair, captured for the prompt archive."""

    timestamp: float
    mode: str  # "chat" or "json"
    model: str
    messages: list[dict[str, str]]
    response: str
    elapsed_s: float


class OllamaClient:
    """Thin wrapper around the Ollama REST API.

    The client keeps an in-memory log of every prompt/response so the
    ``--demo`` mode can dump a reproducible transcript for video evidence.
    """

    def __init__(self, config: OllamaConfig | None = None) -> None:
        self.config = config or OllamaConfig()
        self.prompt_log: list[PromptLogEntry] = []

    # ------------------------------------------------------------------
    # Health / discovery
    # ------------------------------------------------------------------
    def ping(self) -> bool:
        """Return True if the Ollama daemon answers on its root endpoint."""
        try:
            response = requests.get(self.config.host, timeout=CONNECT_TIMEOUT_S)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> list[str]:
        """List locally pulled model names. Empty list on failure."""
        try:
            response = requests.get(
                f"{self.config.host}/api/tags",
                timeout=(CONNECT_TIMEOUT_S, 10),
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            return []
        return [m.get("name", "") for m in payload.get("models", []) if m.get("name")]

    def has_model(self, name: str) -> bool:
        """True if ``name`` (or its base tag) is in the local model list."""
        local = self.list_models()
        if name in local:
            return True
        # Be lenient: "llama3.2:3b" and "llama3.2:3b-instruct" should both
        # match a request for "llama3.2:3b". Compare by family prefix too.
        base = name.split(":", 1)[0]
        for m in local:
            if m == name:
                return True
            if m.split(":", 1)[0] == base and ":" not in name:
                return True
        return False

    # ------------------------------------------------------------------
    # Auto-launch + warmup
    # ------------------------------------------------------------------
    def ensure_daemon(
        self,
        timeout_s: float = 25.0,
        on_status: Callable[[str], None] | None = None,
    ) -> bool:
        """Make the daemon reachable, starting it ourselves if needed.

        Returns True on success. ``on_status`` is invoked with short
        human-readable strings so the UI can surface progress while the
        function blocks the calling (background) thread.
        """
        def status(msg: str) -> None:
            if on_status is not None:
                on_status(msg)

        if self.ping():
            return True
        executable = find_ollama_executable()
        if executable is None:
            status(
                "Ollama not installed. Get it at https://ollama.com/download"
            )
            return False
        status("Starting Ollama in the background...")
        if not _spawn_daemon(executable):
            status("Failed to start Ollama. Open it manually and retry.")
            return False
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.ping():
                status("Ollama is up.")
                return True
            time.sleep(0.4)
        status(
            "Ollama did not respond in time. Try launching the Ollama app "
            "manually, then click Settings -> 'Re-check Ollama'."
        )
        return False

    def pull_model(
        self,
        name: str,
        on_progress: Callable[[str], None] | None = None,
    ) -> bool:
        """Pull a model from the Ollama registry, streaming progress.

        ``on_progress`` is called with throttled human-readable strings
        ("downloading 30%"); the caller does not need to throttle itself.
        Returns True on success.
        """
        def report(msg: str) -> None:
            if on_progress is not None:
                on_progress(msg)

        url = f"{self.config.host}/api/pull"
        try:
            response = requests.post(
                url,
                json={"name": name, "stream": True},
                stream=True,
                # No read timeout: a fresh pull can run for minutes on a
                # slow connection. The connect timeout still protects us
                # against a daemon that isn't actually up.
                timeout=(CONNECT_TIMEOUT_S, None),
            )
        except requests.RequestException as exc:
            report(f"Pull transport error: {exc}")
            return False
        if response.status_code != 200:
            report(
                f"Pull HTTP {response.status_code}: {response.text[:200]}"
            )
            return False
        last_emit = 0.0
        success = False
        for raw in response.iter_lines(decode_unicode=True):
            if not raw:
                continue
            try:
                evt = json.loads(raw)
            except ValueError:
                continue
            if "error" in evt:
                report(f"Pull error: {evt['error']}")
                return False
            status = str(evt.get("status", "")).strip()
            total = evt.get("total")
            completed = evt.get("completed")
            now = time.monotonic()
            # Throttle: at most ~3 status updates per second to keep the
            # toast stack readable.
            if now - last_emit > 0.35 or status in {"success", "pulling manifest"}:
                if total and completed:
                    pct = int(100 * completed / total)
                    report(f"Pulling {name}: {status} {pct}%")
                else:
                    report(f"Pulling {name}: {status}")
                last_emit = now
            if status == "success":
                success = True
        return success

    def warmup(self, num_predict: int = 1) -> None:
        """Run a tiny generation so the model is hot for the first chat.

        Failures are swallowed: warmup is a nice-to-have, not a
        precondition. The keep-alive header keeps the model resident
        for ``self.config.keep_alive`` after it loads.
        """
        url = f"{self.config.host}/api/chat"
        body = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": "Reply with 'ok'."}],
            "stream": False,
            "keep_alive": self.config.keep_alive,
            "options": {"num_predict": max(1, int(num_predict)), "temperature": 0.0},
        }
        try:
            requests.post(
                url,
                json=body,
                timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S),
            )
        except requests.RequestException:
            pass

    # ------------------------------------------------------------------
    # Streaming chat
    # ------------------------------------------------------------------
    def chat_stream(
        self,
        messages: list[dict[str, str]],
        on_token: Callable[[str], None] | None = None,
    ) -> Iterator[str]:
        """Yield response tokens as they arrive.

        Used for the free-form persona chat path. Tokens are also collected
        and the full response is appended to ``prompt_log`` once the stream
        finishes so we can replay any conversation later.

        ``on_token`` is an optional sink for callers that prefer a callback
        (handy for the typewriter UI which already pumps the Pygame event
        loop and just needs a side-effect per chunk).
        """
        url = f"{self.config.host}/api/chat"
        body = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.config.keep_alive,
            "options": self._chat_options(),
        }
        started = time.time()
        chunks: list[str] = []
        try:
            with requests.post(
                url,
                json=body,
                stream=True,
                timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S),
            ) as response:
                if response.status_code != 200:
                    raise OllamaError(
                        f"Ollama chat returned {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if payload.get("error"):
                        raise OllamaError(str(payload["error"]))
                    token = payload.get("message", {}).get("content", "")
                    if token:
                        chunks.append(token)
                        if on_token is not None:
                            on_token(token)
                        yield token
                    if payload.get("done"):
                        break
        except requests.RequestException as exc:
            raise OllamaError(f"Ollama chat transport error: {exc}") from exc
        finally:
            self.prompt_log.append(
                PromptLogEntry(
                    timestamp=started,
                    mode="chat",
                    model=self.config.model,
                    messages=messages,
                    response="".join(chunks),
                    elapsed_s=time.time() - started,
                )
            )

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Convenience wrapper that joins a streamed reply into one string."""
        return "".join(self.chat_stream(messages))

    # ------------------------------------------------------------------
    # JSON-mode call (decisions)
    # ------------------------------------------------------------------
    def json_call(
        self,
        messages: list[dict[str, str]],
        schema_hint: str = "",
    ) -> str:
        """Run a non-streamed call constrained to JSON output.

        Returns the raw JSON string. Validation/parsing happens in
        ``parsers.py`` so this layer stays free of game-specific schema.
        """
        url = f"{self.config.host}/api/chat"
        body = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "keep_alive": self.config.keep_alive,
            "options": self._json_options(),
        }
        started = time.time()
        try:
            response = requests.post(
                url,
                json=body,
                timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S),
            )
        except requests.RequestException as exc:
            raise OllamaError(f"Ollama json transport error: {exc}") from exc
        if response.status_code != 200:
            raise OllamaError(
                f"Ollama json returned {response.status_code}: "
                f"{response.text[:200]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise OllamaError("Ollama returned non-JSON envelope") from exc
        content = payload.get("message", {}).get("content", "")
        self.prompt_log.append(
            PromptLogEntry(
                timestamp=started,
                mode="json",
                model=self.config.model,
                messages=messages + [{"role": "system", "schema": schema_hint}],
                response=content,
                elapsed_s=time.time() - started,
            )
        )
        return content

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _chat_options(self) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "temperature": self.config.chat_temperature,
            # Slightly trimmed top_p keeps replies coherent without killing
            # variety. Tuned during prototype play-tests; see prompts-used.md.
            "top_p": 0.9,
        }
        if self.config.seed is not None:
            opts["seed"] = self.config.seed
        opts.update(self.config.extra_options)
        return opts

    def _json_options(self) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "temperature": self.config.json_temperature,
            "top_p": 0.8,
        }
        if self.config.seed is not None:
            opts["seed"] = self.config.seed
        opts.update(self.config.extra_options)
        return opts

    # ------------------------------------------------------------------
    # Prompt log helpers (used by --demo mode and tests)
    # ------------------------------------------------------------------
    def dump_log_jsonl(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            for entry in self.prompt_log:
                fh.write(
                    json.dumps(
                        {
                            "timestamp": entry.timestamp,
                            "mode": entry.mode,
                            "model": entry.model,
                            "messages": entry.messages,
                            "response": entry.response,
                            "elapsed_s": round(entry.elapsed_s, 3),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def reset_log(self) -> None:
        self.prompt_log.clear()
