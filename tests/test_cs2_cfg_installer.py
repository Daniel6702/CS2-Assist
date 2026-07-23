from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.optional_dependency_stubs import install_mss_stub, install_pynput_stub

install_mss_stub()
install_pynput_stub()

from app.cs2_integration.cfg_installer import (
    AUTOEXEC_BLOCK_BEGIN,
    AUTOEXEC_BLOCK_END,
    COMMAND_SLOT_COUNT,
    InvalidGameRootError,
    cfg_dir_for_game_root,
    install_cfg_files,
    validate_game_root,
)


class CfgInstallerTests(unittest.TestCase):
    def test_cfg_dir_for_game_root_points_to_csgo_cfg_when_root_given(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            cfg_dir = cfg_dir_for_game_root(root)

        self.assertEqual(cfg_dir, root / "game" / "csgo" / "cfg")

    def test_validate_game_root_rejects_missing_cfg_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            with self.assertRaises(InvalidGameRootError):
                validate_game_root(root)

            self.assertFalse((root / "autoexec.cfg").exists())
            self.assertFalse((root / "game").exists())

    def test_install_cfg_files_creates_gsi_bootstrap_slots_and_autoexec(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._valid_game_root(Path(temp_dir))

            result = install_cfg_files(root)

            self.assertEqual(result.cfg_dir, root / "game" / "csgo" / "cfg")
            self.assertTrue((result.cfg_dir / "gamestate_integration_cs2_assist.cfg").exists())
            self.assertIn("bind scancode104 exec cs2assist_cmd_01", result.bootstrap_path.read_text())
            self.assertIn("exec cs2assist_bootstrap", result.autoexec_path.read_text())
            self.assertEqual(len(result.command_slot_paths), COMMAND_SLOT_COUNT)
            self.assertEqual(result.command_slot_paths[0].name, "cs2assist_cmd_01.cfg")
            self.assertEqual(result.command_slot_paths[-1].name, "cs2assist_cmd_12.cfg")

    def test_install_cfg_files_enables_console_logging_in_managed_autoexec_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._valid_game_root(Path(temp_dir))

            result = install_cfg_files(root)

            autoexec_text = result.autoexec_path.read_text()
            self.assertIn("conclearlog", autoexec_text)
            self.assertIn("condebug", autoexec_text)
            self.assertIn("exec cs2assist_bootstrap", autoexec_text)

    def test_install_cfg_files_preserves_autoexec_and_creates_single_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._valid_game_root(Path(temp_dir))
            cfg_dir = cfg_dir_for_game_root(root)
            autoexec = cfg_dir / "autoexec.cfg"
            original = "fps_max 400\n"
            autoexec.write_text(original)

            first = install_cfg_files(root)
            second = install_cfg_files(root)

            autoexec_text = autoexec.read_text()
            self.assertTrue(first.autoexec_backup_path.exists())
            self.assertEqual(first.autoexec_backup_path, second.autoexec_backup_path)
            self.assertEqual(first.autoexec_backup_path.read_text(), original)
            self.assertTrue(autoexec_text.startswith(original))
            self.assertEqual(autoexec_text.count(AUTOEXEC_BLOCK_BEGIN), 1)
            self.assertEqual(autoexec_text.count(AUTOEXEC_BLOCK_END), 1)

    def test_install_cfg_files_does_not_overwrite_existing_command_slot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._valid_game_root(Path(temp_dir))
            existing_slot = cfg_dir_for_game_root(root) / "cs2assist_cmd_07.cfg"
            existing_slot.write_text("say keep me")

            install_cfg_files(root)

            self.assertEqual(existing_slot.read_text(), "say keep me")

    @staticmethod
    def _valid_game_root(root: Path) -> Path:
        (root / "game" / "csgo" / "cfg").mkdir(parents=True)
        return root


if __name__ == "__main__":
    _ = unittest.main()
