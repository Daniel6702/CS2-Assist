from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from app.cs2_integration.settings import AppSettings, load_settings, save_settings  # noqa: E402
from app.main import create_command_bridge, setup_required  # noqa: E402
from app.ui.setup_dialog import CS2SetupDialog  # noqa: E402


class SetupDialogTests(unittest.TestCase):
    def test_invalid_root_shows_retryable_error_without_saving(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / "state"
            dialog = CS2SetupDialog(state_dir=state_dir)
            try:
                dialog.path_edit.setText(temp_dir)

                accepted = dialog.try_setup()

                self.assertFalse(accepted)
                self.assertIn("CS2 cfg folder not found", dialog.error_label.text())
                self.assertEqual(load_settings(state_dir), AppSettings())
            finally:
                dialog.close()
                dialog.deleteLater()
                app.processEvents()

    def test_valid_root_installs_cfg_files_and_saves_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "cs2"
            (root / "game" / "csgo" / "cfg").mkdir(parents=True)
            state_dir = Path(temp_dir) / "state"
            dialog = CS2SetupDialog(state_dir=state_dir)
            try:
                dialog.path_edit.setText(str(root))

                accepted = dialog.try_setup()

                self.assertTrue(accepted)
                self.assertEqual(load_settings(state_dir), AppSettings(cs2_game_root=str(root)))
                self.assertTrue((root / "game" / "csgo" / "cfg" / "cs2assist_bootstrap.cfg").exists())
            finally:
                dialog.close()
                dialog.deleteLater()
                app.processEvents()

    def test_launcher_uses_counter_strike_2_wording(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dialog = CS2SetupDialog(state_dir=Path(temp_dir) / "profiles")
            try:
                self.assertIn("Counter-Strike 2", dialog.path_edit.placeholderText())
                self.assertNotIn("Counter-Strike Global Offensive", dialog.path_edit.placeholderText())
            finally:
                dialog.close()
                dialog.deleteLater()
                app.processEvents()

    def test_launcher_prefills_saved_game_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / "profiles"
            saved_root = Path(temp_dir) / "Counter-Strike 2"
            save_settings(AppSettings(cs2_game_root=str(saved_root)), state_dir)

            dialog = CS2SetupDialog(state_dir=state_dir)
            try:
                self.assertEqual(dialog.path_edit.text(), str(saved_root))
            finally:
                dialog.close()
                dialog.deleteLater()
                app.processEvents()

    def test_setup_required_tracks_missing_invalid_and_valid_saved_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / "state"
            valid_root = Path(temp_dir) / "valid"
            (valid_root / "game" / "csgo" / "cfg").mkdir(parents=True)

            self.assertTrue(setup_required(state_dir))

            save_settings(AppSettings(cs2_game_root=str(Path(temp_dir) / "invalid")), state_dir)
            self.assertTrue(setup_required(state_dir))

            save_settings(AppSettings(cs2_game_root=str(valid_root)), state_dir)
            self.assertFalse(setup_required(state_dir))

    def test_create_command_bridge_uses_saved_valid_cfg_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / "state"
            root = Path(temp_dir) / "valid"
            cfg_dir = root / "game" / "csgo" / "cfg"
            cfg_dir.mkdir(parents=True)
            save_settings(AppSettings(cs2_game_root=str(root)), state_dir)

            bridge = create_command_bridge(state_dir)
            try:
                self.assertIsNotNone(bridge)
                assert bridge is not None
                self.assertEqual(bridge.cfg_dir, cfg_dir)
            finally:
                if bridge is not None:
                    bridge.close()


if __name__ == "__main__":
    _ = unittest.main()
