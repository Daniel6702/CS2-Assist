from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets


class KillSoundSection(QtWidgets.QGroupBox):
    changed = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Kill Sound", parent)
        self.setStyleSheet("QGroupBox { font-weight: 600; }")
        form = QtWidgets.QFormLayout(self)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.enabled = QtWidgets.QCheckBox()
        self.enabled.stateChanged.connect(self.changed)
        form.addRow("Enabled", self.enabled)

        file_row = QtWidgets.QHBoxLayout()
        self.file = QtWidgets.QLineEdit()
        self.file.setPlaceholderText("Select a sound file (.mp3, .wav, .ogg ...)")
        self.file.editingFinished.connect(self.changed)
        file_row.addWidget(self.file, 1)
        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        file_row.addWidget(browse_btn)
        form.addRow("Sound file", file_row)

        self.volume = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(50)
        self.volume.valueChanged.connect(self.changed)
        self.volume_label = QtWidgets.QLabel("50%")
        self.volume.valueChanged.connect(lambda value: self.volume_label.setText(f"{value}%"))
        volume_row = QtWidgets.QHBoxLayout()
        volume_row.addWidget(self.volume, 1)
        volume_row.addWidget(self.volume_label)
        form.addRow("Volume", volume_row)

        test_btn = QtWidgets.QPushButton("Test Sound")
        test_btn.clicked.connect(self._test)
        form.addRow("", test_btn)

    def load_config(self, config: dict[str, Any]) -> None:
        self.enabled.setChecked(bool(config.get("enabled", False)))
        self.file.setText(str(config.get("sound_file", "") or ""))
        volume = int(config.get("volume", 50))
        self.volume.setValue(max(0, min(100, volume)))

    def extract_config(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled.isChecked(),
            "sound_file": self.file.text().strip(),
            "volume": self.volume.value(),
        }

    def _browse(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Kill Sound",
            "",
            "Audio Files (*.mp3 *.wav *.ogg *.flac *.aac);;All Files (*)",
        )
        if path:
            self.file.setText(path)
            self.changed.emit()

    def _test(self) -> None:
        from app.components.kill_sound import KillSoundComponent

        path = self.file.text().strip()
        if path:
            KillSoundComponent._play(path, self.volume.value())
