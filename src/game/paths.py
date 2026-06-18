"""Resolve read-only bundle paths vs writable user-data paths.

In development, bundle assets live at the project root and user data
under ``data/``. In a PyInstaller build, bundled assets are extracted to
``sys._MEIPASS`` while saves and settings sit next to the executable.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def bundle_root() -> Path:
    """Root directory for read-only game assets."""
    if _is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # src/game/paths.py -> project root is three levels up.
    return Path(__file__).resolve().parents[2]


def user_data_dir() -> Path:
    """Writable folder for saves and settings."""
    if _is_frozen():
        root = Path(sys.executable).resolve().parent
    else:
        root = bundle_root() / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def saves_dir() -> Path:
    """Directory holding slot save files."""
    path = user_data_dir() / "saves"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_slot_path(slot: int) -> Path:
    """Path for save slot 1..3."""
    if slot not in (1, 2, 3):
        raise ValueError(f"save slot must be 1..3, got {slot}")
    return saves_dir() / f"slot_{slot}.json"


def settings_path() -> Path:
    return user_data_dir() / "settings.json"


def legacy_savegame_path() -> Path:
    """Pre-slot single-file save used by older builds."""
    if _is_frozen():
        return user_data_dir() / "savegame.json"
    return bundle_root() / "data" / "savegame.json"


def data_dir() -> Path:
    """Read-only ``data/`` tree (personas, items)."""
    return bundle_root() / "data"


def personas_dir() -> Path:
    return data_dir() / "personas"


def items_path() -> Path:
    return data_dir() / "items.json"


def assets_dir() -> Path:
    return bundle_root() / "assets"


def bundled_music_dir() -> Path:
    return bundle_root() / "Music"


def user_music_dir() -> Path:
    """Optional drop-in music beside the exe (or project root in dev)."""
    if _is_frozen():
        return Path(sys.executable).resolve().parent / "Music"
    return bundle_root() / "Music"


def migrate_legacy_save_if_needed() -> None:
    """Copy legacy ``savegame.json`` into slot 1 when slots are all empty."""
    legacy = legacy_savegame_path()
    if not legacy.is_file():
        return
    if any(save_slot_path(s).is_file() for s in (1, 2, 3)):
        return
    target = save_slot_path(1)
    shutil.copy2(legacy, target)
