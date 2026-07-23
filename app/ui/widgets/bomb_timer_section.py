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

        left = QtWidgets.QVBoxLayout()
        left.setSpacing(4)
        outer.addLayout(left)

        self.enabled = QtWidgets.QCheckBox("Enabled")
        self.enabled.stateChanged.connect(self.changed)
        left.addWidget(self.enabled)
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
        left.addSpacing(6)

        visual_row = QtWidgets.QHBoxLayout()
        visual_row.setSpacing(16)
        self.font_size = QtWidgets.QSpinBox()
        self.font_size.setRange(12, 200)
        self.font_size.setValue(48)
        self.font_size.valueChanged.connect(self.changed)
        visual_row.addWidget(QtWidgets.QLabel("Font size:"))
        visual_row.addWidget(self.font_size)

        self.color_btn = QtWidgets.QPushButton()
        self.color_btn.setFixedSize(32, 24)
        self.color_btn.clicked.connect(self._pick_color)
        self._color = QtGui.QColor(255, 50, 50)
        self._update_color_button()
        visual_row.addWidget(QtWidgets.QLabel("Text colour:"))
        visual_row.addWidget(self.color_btn)
        visual_row.addStretch(1)
        left.addLayout(visual_row)
        left.addStretch(1)

    def load_config(self, config: dict[str, Any]) -> None:
        self.enabled.setChecked(bool(config.get("enabled", False)))
        self.timer_seconds.setValue(int(config.get("timer_seconds", 40)))
        self.font_size.setValue(int(config.get("overlay_font_size", 48)))
        raw_color = config.get("overlay_color", "#FF3232")
        if isinstance(raw_color, str):
            self._color = QtGui.QColor(raw_color)
        self._update_color_button()

    def extract_config(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled.isChecked(),
            "timer_seconds": self.timer_seconds.value(),
            "overlay_font_size": self.font_size.value(),
            "overlay_color": self._color.name(),
        }

    def _pick_color(self) -> None:
        color = QtWidgets.QColorDialog.getColor(self._color, self, "Select Timer Colour")
        if color.isValid():
            self._color = color
            self._update_color_button()
            self.changed.emit()

    def _update_color_button(self) -> None:
        self.color_btn.setStyleSheet(f"background-color: {self._color.name()}; border: 1px solid #888;")
