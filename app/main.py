from __future__ import annotations

import sys
from pathlib import Path

from PySide6 import QtWidgets

from app.cs2_integration.cfg_installer import InvalidGameRootError, cfg_dir_for_game_root, validate_game_root
from app.cs2_integration.command_bridge import CS2CommandBridge
from app.cs2_integration.settings import SETTINGS_DIR, load_settings
from app.ui.main_window import MainWindow
from app.ui.setup_dialog import CS2SetupDialog
from app.ui.styles import apply_style


def setup_required(state_dir: Path = SETTINGS_DIR) -> bool:
    settings = load_settings(state_dir)
    if not settings.cs2_game_root:
        return True
    try:
        validate_game_root(Path(settings.cs2_game_root))
    except InvalidGameRootError:
        return True
    return False


def run_setup_dialog(state_dir: Path = SETTINGS_DIR) -> bool:
    dialog = CS2SetupDialog(state_dir=state_dir)
    return dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted


def create_command_bridge(state_dir: Path = SETTINGS_DIR) -> CS2CommandBridge | None:
    settings = load_settings(state_dir)
    if not settings.cs2_game_root:
        return None
    root = Path(settings.cs2_game_root)
    try:
        validate_game_root(root)
    except InvalidGameRootError:
        return None
    return CS2CommandBridge(cfg_dir_for_game_root(root))


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    apply_style(app)
    if setup_required() and not run_setup_dialog():
        return
    window = MainWindow(command_bridge=create_command_bridge())
    window.show()
    sys.exit(app.exec())
