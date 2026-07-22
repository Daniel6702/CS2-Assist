from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from app.cs2_integration.cfg_installer import InvalidGameRootError, install_cfg_files
from app.cs2_integration.settings import SETTINGS_DIR, AppSettings, load_settings, save_settings


class CS2SetupDialog(QtWidgets.QDialog):
    def __init__(self, state_dir: Path = SETTINGS_DIR, parent=None) -> None:
        super().__init__(parent)
        self.state_dir = state_dir
        self.setWindowTitle("CS2 Assist Setup")
        self.setModal(True)
        self.resize(560, 180)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        intro = QtWidgets.QLabel(
            "Enter your CS2 game root folder. It must contain game/csgo/cfg.",
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        row = QtWidgets.QHBoxLayout()
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.setPlaceholderText("/path/to/Counter-Strike 2")
        settings = load_settings(self.state_dir)
        if settings.cs2_game_root:
            self.path_edit.setText(settings.cs2_game_root)
        row.addWidget(self.path_edit, 1)

        browse_btn = QtWidgets.QPushButton("Browse")
        browse_btn.clicked.connect(self._browse)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        self.error_label = QtWidgets.QLabel("")
        self.error_label.setStyleSheet("color: #ff6b6b;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        buttons = QtWidgets.QDialogButtonBox()
        self.next_btn = buttons.addButton("Next", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_btn = buttons.addButton(QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self.next_btn.clicked.connect(self.try_setup)
        self.cancel_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def try_setup(self) -> bool:
        root = Path(self.path_edit.text().strip()).expanduser()
        try:
            install_cfg_files(root)
        except InvalidGameRootError as exc:
            self.error_label.setText(str(exc))
            return False
        except OSError as exc:
            self.error_label.setText(f"Failed to install CS2 cfg files: {exc}")
            return False
        save_settings(AppSettings(cs2_game_root=str(root)), self.state_dir)
        self.error_label.setText("")
        self.accept()
        return True

    def _browse(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select CS2 game folder",
            self.path_edit.text().strip(),
            QtWidgets.QFileDialog.Option.ShowDirsOnly,
        )
        if selected:
            self.path_edit.setText(selected)
