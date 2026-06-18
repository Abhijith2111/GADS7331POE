"""Tests for bundle vs user-data path resolution."""

from __future__ import annotations

from pathlib import Path

from src.game import paths


def test_save_slot_path_dev_layout() -> None:
    p = paths.save_slot_path(2)
    assert p.name == "slot_2.json"
    assert p.parent.name == "saves"
    # In dev mode user data lives under project data/.
    assert "data" in p.parts
    assert "saves" in p.parts


def test_settings_path_under_user_data() -> None:
    sp = paths.settings_path()
    assert sp.name == "settings.json"
    assert sp.parent == paths.user_data_dir()


def test_personas_dir_under_bundle() -> None:
    pd = paths.personas_dir()
    assert pd.name == "personas"
    assert (pd.parent / "items.json") == paths.items_path()


def test_migrate_legacy_only_when_slots_empty(tmp_path: Path, monkeypatch) -> None:
    legacy = tmp_path / "data" / "savegame.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"gold": 99}', encoding="utf-8")
    user_data = tmp_path / "userdata"
    user_data.mkdir()
    saves = user_data / "saves"
    saves.mkdir()

    monkeypatch.setattr(paths, "bundle_root", lambda: tmp_path)
    monkeypatch.setattr(paths, "user_data_dir", lambda: user_data)
    monkeypatch.setattr(
        paths,
        "legacy_savegame_path",
        lambda: legacy,
    )
    monkeypatch.setattr(
        paths,
        "save_slot_path",
        lambda slot: saves / f"slot_{slot}.json",
    )

    paths.migrate_legacy_save_if_needed()
    slot1 = saves / "slot_1.json"
    assert slot1.is_file()
    assert "99" in slot1.read_text(encoding="utf-8")
