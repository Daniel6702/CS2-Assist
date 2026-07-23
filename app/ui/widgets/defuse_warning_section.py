from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets


class DefuseWarningSection(QtWidgets.QGroupBox):
    changed = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Defuse Warning", parent)
        self.setStyleSheet("QGroupBox { font-weight: 600; }")
        outer = QtWidgets.QVBoxLayout(self)
        outer.setSpacing(6)

        self.defuse_warn = QtWidgets.QCheckBox("CT defuse out-of-time warning overlay")
        self.defuse_warn.setChecked(True)
        self.defuse_warn.stateChanged.connect(self.changed)
        outer.addWidget(self.defuse_warn)

        outer.addWidget(QtWidgets.QLabel("Warning sounds:"))
        self.warn10_enabled, self.warn10_file, self.warn10_volume = self._add_warning_sound(
            outer, "10 seconds remaining", "Select 10s Warning Sound"
        )
        self.warn5_enabled, self.warn5_file, self.warn5_volume = self._add_warning_sound(
            outer, "5 seconds remaining", "Select 5s Warning Sound"
        )
        outer.addStretch(1)

    def load_config(self, config: dict[str, Any]) -> None:
        self.defuse_warn.setChecked(bool(config.get("defuse_warning_enabled", True)))
        self.warn10_enabled.setChecked(bool(config.get("warning_10s_enabled", True)))
        self.warn10_file.setText(str(config.get("warning_10s_file", "") or ""))
        self.warn10_volume.setValue(max(0, min(100, int(config.get("warning_10s_volume", 50)))))
        self.warn5_enabled.setChecked(bool(config.get("warning_5s_enabled", True)))
        self.warn5_file.setText(str(config.get("warning_5s_file", "") or ""))
        self.warn5_volume.setValue(max(0, min(100, int(config.get("warning_5s_volume", 50)))))

    def extract_config(self) -> dict[str, Any]:
        return {
            "defuse_warning_enabled": self.defuse_warn.isChecked(),
            "warning_10s_enabled": self.warn10_enabled.isChecked(),
            "warning_10s_file": self.warn10_file.text().strip(),
            "warning_10s_volume": self.warn10_volume.value(),
            "warning_5s_enabled": self.warn5_enabled.isChecked(),
            "warning_5s_file": self.warn5_file.text().strip(),
            "warning_5s_volume": self.warn5_volume.value(),
        }

    def _add_warning_sound(
        self, parent: QtWidgets.QVBoxLayout, label: str, dialog_title: str
    ) -> tuple[QtWidgets.QCheckBox, QtWidgets.QLineEdit, QtWidgets.QSlider]:
        row = QtWidgets.QHBoxLayout()
        checkbox = QtWidgets.QCheckBox(label)
        checkbox.stateChanged.connect(self.changed)
        row.addWidget(checkbox)
        file_edit = QtWidgets.QLineEdit()
        file_edit.setPlaceholderText("Sound file ...")
        file_edit.editingFinished.connect(self.changed)
        row.addWidget(file_edit, 1)
        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.clicked.connect(lambda: self._browse_warning(dialog_title, file_edit))
        row.addWidget(browse_btn)
        volume = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        volume.setRange(0, 100)
        volume.setValue(50)
        volume.valueChanged.connect(self.changed)
        volume_label = QtWidgets.QLabel("50%")
        volume.valueChanged.connect(lambda value: volume_label.setText(f"{value}%"))
        row.addWidget(volume)
        row.addWidget(volume_label)
        parent.addLayout(row)
        return checkbox, file_edit, volume

    def _browse_warning(self, title: str, target: QtWidgets.QLineEdit) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, title, "", "Audio Files (*.mp3 *.wav *.ogg *.flac *.aac);;All Files (*)"
        )
        if path:
            target.setText(path)
            self.changed.emit()
