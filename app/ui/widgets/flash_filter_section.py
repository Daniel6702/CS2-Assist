from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from app.components.flash_filter import DEFAULT_BRIGHTNESS_FACTOR, DEFAULT_FADE_SECONDS, DEFAULT_GAMMA_BLUE, DEFAULT_GAMMA_GREEN, DEFAULT_GAMMA_RED
from app.platform.xrandr import XrandrError, list_connected_outputs
from app.ui.widgets.collapsible_box import CollapsibleBox


class FlashFilterSection(QtWidgets.QGroupBox):
    changed = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Flash Filter", parent)
        self.setStyleSheet("QGroupBox { font-weight: 600; }")
        outer = QtWidgets.QVBoxLayout(self)
        outer.setSpacing(6)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        outer.addLayout(form)

        self.enabled = QtWidgets.QCheckBox()
        self.enabled.stateChanged.connect(self.changed)
        form.addRow("Enabled", self.enabled)

        output_row = QtWidgets.QHBoxLayout()
        self.output = QtWidgets.QComboBox()
        self.output.currentIndexChanged.connect(self.changed)
        output_row.addWidget(self.output, 1)
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_outputs)
        output_row.addWidget(refresh_btn)
        form.addRow("Display output", output_row)

        advanced = CollapsibleBox("Advanced")
        advanced_form = QtWidgets.QFormLayout()
        advanced_form.setHorizontalSpacing(12)
        advanced_form.setVerticalSpacing(8)
        advanced.content_layout.addLayout(advanced_form)
        outer.addWidget(advanced)

        self.brightness_factor = QtWidgets.QDoubleSpinBox()
        self.brightness_factor.setRange(0.05, 1.0)
        self.brightness_factor.setDecimals(2)
        self.brightness_factor.setSingleStep(0.05)
        self.brightness_factor.valueChanged.connect(self.changed)
        advanced_form.addRow("Max brightness factor", self.brightness_factor)

        self.gamma_red = self._gamma_spin()
        self.gamma_green = self._gamma_spin()
        self.gamma_blue = self._gamma_spin()
        advanced_form.addRow("Gamma red multiplier", self.gamma_red)
        advanced_form.addRow("Gamma green multiplier", self.gamma_green)
        advanced_form.addRow("Gamma blue multiplier", self.gamma_blue)

        self.fade_seconds = QtWidgets.QDoubleSpinBox()
        self.fade_seconds.setRange(0.05, 10.0)
        self.fade_seconds.setDecimals(2)
        self.fade_seconds.setSingleStep(0.05)
        self.fade_seconds.setSuffix(" s")
        self.fade_seconds.valueChanged.connect(self.changed)
        advanced_form.addRow("Fade time", self.fade_seconds)

        self._refresh_outputs()

    def load_config(self, config: dict[str, Any]) -> None:
        self.enabled.setChecked(bool(config.get("enabled", False)))
        output = str(config.get("output", "") or "")
        self._refresh_outputs(output)
        self.brightness_factor.setValue(
            max(0.05, min(1.0, float(config.get("brightness_factor", DEFAULT_BRIGHTNESS_FACTOR) or DEFAULT_BRIGHTNESS_FACTOR)))
        )
        self.gamma_red.setValue(max(0.05, min(5.0, float(config.get("gamma_red", DEFAULT_GAMMA_RED) or DEFAULT_GAMMA_RED))))
        self.gamma_green.setValue(max(0.05, min(5.0, float(config.get("gamma_green", DEFAULT_GAMMA_GREEN) or DEFAULT_GAMMA_GREEN))))
        self.gamma_blue.setValue(max(0.05, min(5.0, float(config.get("gamma_blue", DEFAULT_GAMMA_BLUE) or DEFAULT_GAMMA_BLUE))))
        self.fade_seconds.setValue(max(0.05, min(10.0, float(config.get("fade_seconds", DEFAULT_FADE_SECONDS) or DEFAULT_FADE_SECONDS))))

    def extract_config(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled.isChecked(),
            "output": str(self.output.currentData() or ""),
            "brightness_factor": self.brightness_factor.value(),
            "gamma_red": self.gamma_red.value(),
            "gamma_green": self.gamma_green.value(),
            "gamma_blue": self.gamma_blue.value(),
            "fade_seconds": self.fade_seconds.value(),
        }

    def _refresh_outputs(self, selected: str = "") -> None:
        current = selected or str(self.output.currentData() or "")
        self.output.blockSignals(True)
        self.output.clear()
        try:
            outputs = list_connected_outputs()
        except (OSError, XrandrError):
            outputs = []
        if not outputs:
            self.output.addItem("No connected outputs found", "")
        for output in outputs:
            self.output.addItem(output, output)
        if current and self.output.findData(current) < 0:
            self.output.addItem(current, current)
        index = self.output.findData(current)
        if index >= 0:
            self.output.setCurrentIndex(index)
        self.output.blockSignals(False)

    def _gamma_spin(self) -> QtWidgets.QDoubleSpinBox:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(0.05, 5.0)
        spin.setDecimals(2)
        spin.setSingleStep(0.05)
        spin.valueChanged.connect(self.changed)
        return spin
