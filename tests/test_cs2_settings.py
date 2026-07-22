from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.cs2_integration.settings import SETTINGS_DIR, AppSettings, load_settings, save_settings, settings_path
from app.defaults import APP_ROOT
from app.profile_store import ProfileStore


class Cs2SettingsTests(unittest.TestCase):
    def test_load_settings_returns_empty_root_when_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)

            settings = load_settings(state_dir)

        self.assertEqual(settings, AppSettings(cs2_game_root=""))

    def test_save_settings_round_trips_game_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            expected = AppSettings(cs2_game_root="/games/Counter-Strike 2")

            save_settings(expected, state_dir)
            actual = load_settings(state_dir)

        self.assertEqual(actual, expected)

    def test_invalid_json_loads_empty_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)
            settings_path(state_dir).parent.mkdir(parents=True, exist_ok=True)
            settings_path(state_dir).write_text("{")

            settings = load_settings(state_dir)

        self.assertEqual(settings, AppSettings(cs2_game_root=""))

    def test_default_settings_file_lives_in_profiles_directory(self) -> None:
        self.assertEqual(settings_path(), APP_ROOT / "profiles" / "settings.json")
        self.assertEqual(SETTINGS_DIR, APP_ROOT / "profiles")

    def test_settings_file_does_not_create_profile_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_root = root / "profiles"
            store = ProfileStore(profile_root)

            save_settings(AppSettings(cs2_game_root="/tmp/cs2"), profile_root)

            self.assertEqual(store.list_profile_names(), ["Default"])
            self.assertTrue(settings_path(profile_root).exists())


if __name__ == "__main__":
    _ = unittest.main()
