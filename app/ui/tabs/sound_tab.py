from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from app.ui.tabs.base import BaseTab


class SoundTab(BaseTab):
    config_changed = QtCore.Signal(str, dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        group = QtWidgets.QGroupBox("Kill Sound")
        group.setStyleSheet("QGroupBox { font-weight: 600; }")
        form = QtWidgets.QFormLayout(group)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        outer.addWidget(group)

        self.enabled = QtWidgets.QCheckBox()
        self.enabled.stateChanged.connect(self._emit_change)
        form.addRow("Enabled", self.enabled)

        file_row = QtWidgets.QHBoxLayout()
        self.file_path = QtWidgets.QLineEdit()
        self.file_path.setPlaceholderText("Select a sound file (.mp3, .wav, .ogg ...)")
        self.file_path.editingFinished.connect(self._emit_change)
        file_row.addWidget(self.file_path, 1)
        self.browse_btn = QtWidgets.QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(self.browse_btn)
        form.addRow("Sound file", file_row)

        self.volume = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(50)
        self.volume.valueChanged.connect(self._emit_change)
        self.volume_label = QtWidgets.QLabel("50%")
        self.volume.valueChanged.connect(lambda v: self.volume_label.setText(f"{v}%"))
        volume_row = QtWidgets.QHBoxLayout()
        volume_row.addWidget(self.volume, 1)
        volume_row.addWidget(self.volume_label)
        form.addRow("Volume", volume_row)

        self.test_btn = QtWidgets.QPushButton("Test Sound")
        self.test_btn.clicked.connect(self._play_test)
        form.addRow("", self.test_btn)

        help_lbl = QtWidgets.QLabel(
            "Requires GSI to be enabled. Plays the selected sound file each time a kill is recorded via GSI."
        )
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: #666;")
        outer.addWidget(help_lbl)

        outer.addStretch(1)

    def _browse_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Kill Sound",
            "",
            "Audio Files (*.mp3 *.wav *.ogg *.flac *.aac);;All Files (*)",
        )
        if path:
            self.file_path.setText(path)
            self._emit_change()

    def _play_test(self) -> None:
        from app.components.kill_sound import KillSoundComponent

        path = self.file_path.text().strip()
        if not path:
            return
        volume = self.volume.value()
        KillSoundComponent._play(path, volume)

    def load_config(self, config: dict[str, Any]) -> None:
        self.enabled.setChecked(bool(config.get("enabled", False)))
        self.file_path.setText(str(config.get("sound_file", "") or ""))
        vol = int(config.get("volume", 50))
        self.volume.setValue(max(0, min(100, vol)))

    def extract_config(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled.isChecked(),
            "sound_file": self.file_path.text().strip(),
            "volume": self.volume.value(),
        }

    def _emit_change(self) -> None:
        self.config_changed.emit("kill_sound", self.extract_config())
