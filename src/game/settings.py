"""Persistent player preferences (volume, window size, last slot)."""



from __future__ import annotations



import json

from dataclasses import dataclass

from pathlib import Path



from .paths import settings_path

from src.llm.ollama_client import DEFAULT_MODEL





DEFAULT_MUSIC_VOLUME = 0.32

DEFAULT_WINDOW = (1920, 1080)





@dataclass

class GameSettings:

    music_volume: float = DEFAULT_MUSIC_VOLUME

    window_width: int = DEFAULT_WINDOW[0]

    window_height: int = DEFAULT_WINDOW[1]

    last_slot: int = 1

    ollama_model: str = DEFAULT_MODEL



    @property

    def window_size(self) -> tuple[int, int]:

        return (self.window_width, self.window_height)



    @classmethod

    def load(cls, path: Path | None = None) -> "GameSettings":

        path = path or settings_path()

        if not path.is_file():

            return cls()

        try:

            with open(path, "r", encoding="utf-8") as fh:

                raw = json.load(fh)

        except (OSError, json.JSONDecodeError, TypeError):

            return cls()

        vol = float(raw.get("music_volume", DEFAULT_MUSIC_VOLUME))

        vol = max(0.0, min(1.0, vol))

        slot = int(raw.get("last_slot", 1))

        slot = max(1, min(3, slot))

        model = str(raw.get("ollama_model", DEFAULT_MODEL)).strip() or DEFAULT_MODEL

        return cls(

            music_volume=vol,

            window_width=int(raw.get("window_width", DEFAULT_WINDOW[0])),

            window_height=int(raw.get("window_height", DEFAULT_WINDOW[1])),

            last_slot=slot,

            ollama_model=model,

        )



    def save(self, path: Path | None = None) -> None:

        path = path or settings_path()

        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {

            "music_volume": round(self.music_volume, 3),

            "window_width": self.window_width,

            "window_height": self.window_height,

            "last_slot": self.last_slot,

            "ollama_model": self.ollama_model,

        }

        with open(path, "w", encoding="utf-8") as fh:

            json.dump(payload, fh, indent=2, ensure_ascii=False)


