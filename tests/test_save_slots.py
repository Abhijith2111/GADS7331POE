"""Tests for three-slot save management and settings."""

from __future__ import annotations

import json
from pathlib import Path

from src.game import paths, save_slots
from src.game.settings import GameSettings


def _patch_user_data(tmp_path: Path, monkeypatch) -> Path:
    user_data = tmp_path / "data"
    user_data.mkdir()
    saves = user_data / "saves"
    saves.mkdir()
    monkeypatch.setattr(paths, "user_data_dir", lambda: user_data)
    monkeypatch.setattr(
        paths,
        "save_slot_path",
        lambda slot: saves / f"slot_{slot}.json",
    )
    monkeypatch.setattr(paths, "settings_path", lambda: user_data / "settings.json")
    monkeypatch.setattr(paths, "migrate_legacy_save_if_needed", lambda: None)
    return saves


def test_read_slot_summary_empty(tmp_path: Path, monkeypatch) -> None:
    _patch_user_data(tmp_path, monkeypatch)
    summary = save_slots.read_slot_summary(1)
    assert summary.exists is False
    assert summary.gold == 0


def test_read_slot_summary_populated(tmp_path: Path, monkeypatch) -> None:
    saves = _patch_user_data(tmp_path, monkeypatch)
    payload = {
        "gold": 42,
        "reputation": {"townsfolk": 0, "wealthy": 0, "underworld": 0},
        "active_quests": [{"title": "A"}],
        "rumour_memory": ["x", "y"],
        "served_personas": ["broke_bard"],
        "gossip_heard": [],
        "rumours_pending": [],
        "completed_quests": [],
        "tavern_supplies": {},
    }
    (saves / "slot_2.json").write_text(json.dumps(payload), encoding="utf-8")
    summary = save_slots.read_slot_summary(2)
    assert summary.exists is True
    assert summary.gold == 42
    assert summary.active_quests == 1
    assert summary.rumour_memory == 2
    assert summary.served_count == 1


def test_create_new_slot_writes_fresh_save(tmp_path: Path, monkeypatch) -> None:
    saves = _patch_user_data(tmp_path, monkeypatch)
    ws = save_slots.create_new_slot(3)
    assert ws.gold == 50
    assert (saves / "slot_3.json").is_file()


def test_settings_round_trip(tmp_path: Path, monkeypatch) -> None:
    _patch_user_data(tmp_path, monkeypatch)
    s = GameSettings(music_volume=0.55, window_width=1280, window_height=880, last_slot=2)
    s.save()
    loaded = GameSettings.load()
    assert loaded.music_volume == 0.55
    assert loaded.window_width == 1280
    assert loaded.last_slot == 2
