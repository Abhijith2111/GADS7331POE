"""Tests for persistent game settings."""

from __future__ import annotations

from src.game.settings import GameSettings, DEFAULT_MUSIC_VOLUME


def test_settings_round_trip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    settings = GameSettings(
        music_volume=0.55,
        window_width=1280,
        window_height=880,
        last_slot=2,
        ollama_model="llama3.2:1b",
    )
    settings.save(path)
    loaded = GameSettings.load(path)
    assert loaded.music_volume == 0.55
    assert loaded.window_width == 1280
    assert loaded.window_height == 880
    assert loaded.last_slot == 2
    assert loaded.ollama_model == "llama3.2:1b"


def test_settings_defaults_when_missing_file(tmp_path) -> None:
    loaded = GameSettings.load(tmp_path / "missing.json")
    assert loaded.music_volume == DEFAULT_MUSIC_VOLUME
    assert loaded.last_slot == 1
