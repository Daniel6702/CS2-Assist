from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets


class BombTimerSection(QtWidgets.QGroupBox):
    changed = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Bomb Timer", parent)
        self.setStyleSheet("QGroupBox { font-weight: 600; }")
        outer = QtWidgets.QVBoxLayout(self)
        outer.setSpacing(6)

        columns = QtWidgets.QHBoxLayout()
        columns.setSpacing(24)
        outer.addLayout(columns)

        left = QtWidgets.QVBoxLayout()
        left.setSpacing(4)
        columns.addLayout(left)

        self.enabled = QtWidgets.QCheckBox("Enabled")
        self.enabled.stateChanged.connect(self.changed)
        left.addWidget(self.enabled)
        left.addSpacing(6)

        size_color_row = QtWidgets.QHBoxLayout()
        size_color_row.setSpacing(16)
        self.font_size = QtWidgets.QSpinBox()
        self.font_size.setRange(12, 200)
        self.font_size.setValue(48)
        self.font_size.valueChanged.connect(self.changed)
        size_color_row.addWidget(QtWidgets.QLabel("Font size:"))
        size_color_row.addWidget(self.font_size)

        self.color_btn = QtWidgets.QPushButton()
        self.color_btn.setFixedSize(32, 24)
        self.color_btn.clicked.connect(self._pick_color)
        self._color = QtGui.QColor(255, 50, 50)
        self._update_color_button()
        size_color_row.addWidget(QtWidgets.QLabel("Text colour:"))
        size_color_row.addWidget(self.color_btn)
        size_color_row.addStretch(1)
        left.addLayout(size_color_row)
        left.addSpacing(6)

        timer_row = QtWidgets.QHBoxLayout()
        self.timer_seconds = QtWidgets.QSpinBox()
        self.timer_seconds.setRange(20, 60)
        self.timer_seconds.setValue(40)
        self.timer_seconds.setSuffix(" sec")
        self.timer_seconds.valueChanged.connect(self.changed)
        timer_row.addWidget(QtWidgets.QLabel("Timer length:"))
        timer_row.addWidget(self.timer_seconds)
        timer_row.addStretch(1)
        left.addLayout(timer_row)
        left.addStretch(1)

        right = QtWidgets.QVBoxLayout()
        right.setSpacing(6)
        columns.addLayout(right)
        self.defuse_warn = QtWidgets.QCheckBox("CT defuse out-of-time warning overlay")
        self.defuse_warn.setChecked(True)
        self.defuse_warn.stateChanged.connect(self.changed)
        right.addWidget(self.defuse_warn)
        right.addSpacing(4)
        right.addWidget(QtWidgets.QLabel("Warning sounds:"))

        self.warn10_enabled, self.warn10_file, self.warn10_volume = self._add_warning_sound(
            right, "10 seconds remaining", "Select 10s Warning Sound"
        )
        self.warn5_enabled, self.warn5_file, self.warn5_volume = self._add_warning_sound(
            right, "5 seconds remaining", "Select 5s Warning Sound"
        )

    def load_config(self, config: dict[str, Any]) -> None:
        self.enabled.setChecked(bool(config.get("enabled", False)))
        self.defuse_warn.setChecked(bool(config.get("defuse_warning_enabled", True)))
        self.font_size.setValue(int(config.get("overlay_font_size", 48)))
        self.timer_seconds.setValue(int(config.get("timer_seconds", 40)))
        raw_color = config.get("overlay_color", "#FF3232")
        if isinstance(raw_color, str):
            self._color = QtGui.QColor(raw_color)
        self._update_color_button()
        self.warn10_enabled.setChecked(bool(config.get("warning_10s_enabled", True)))
        self.warn10_file.setText(str(config.get("warning_10s_file", "") or ""))
        self.warn10_volume.setValue(max(0, min(100, int(config.get("warning_10s_volume", 50)))))
        self.warn5_enabled.setChecked(bool(config.get("warning_5s_enabled", True)))
        self.warn5_file.setText(str(config.get("warning_5s_file", "") or ""))
        self.warn5_volume.setValue(max(0, min(100, int(config.get("warning_5s_volume", 50)))))

    def extract_config(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled.isChecked(),
            "defuse_warning_enabled": self.defuse_warn.isChecked(),
            "overlay_font_size": self.font_size.value(),
            "overlay_color": self._color.name(),
            "timer_seconds": self.timer_seconds.value(),
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

    def _pick_color(self) -> None:
        color = QtWidgets.QColorDialog.getColor(self._color, self, "Select Timer Colour")
        if color.isValid():
            self._color = color
            self._update_color_button()
            self.changed.emit()

    def _update_color_button(self) -> None:
        self.color_btn.setStyleSheet(f"background-color: {self._color.name()}; border: 1px solid #888;")
