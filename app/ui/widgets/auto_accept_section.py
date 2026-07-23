from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets


class AutoAcceptSection(QtWidgets.QGroupBox):
    changed = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Auto Accept", parent)
        self.setStyleSheet("QGroupBox { font-weight: 600; }")
        form = QtWidgets.QFormLayout(self)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.enabled = QtWidgets.QCheckBox()
        self.enabled.stateChanged.connect(self.changed)
        form.addRow("Enabled", self.enabled)

        self.waiting_time = QtWidgets.QDoubleSpinBox()
        self.waiting_time.setRange(0.1, 30.0)
        self.waiting_time.setDecimals(1)
        self.waiting_time.setSingleStep(0.5)
        self.waiting_time.setValue(5.0)
        self.waiting_time.setSuffix(" s")
        self.waiting_time.valueChanged.connect(self.changed)
        form.addRow("Wait window", self.waiting_time)

        self.hold_ms = QtWidgets.QSpinBox()
        self.hold_ms.setRange(1, 200)
        self.hold_ms.setValue(24)
        self.hold_ms.setSuffix(" ms")
        self.hold_ms.valueChanged.connect(self.changed)
        form.addRow("Click hold", self.hold_ms)

    def load_config(self, config: dict[str, Any]) -> None:
        self.enabled.setChecked(bool(config.get("enabled", False)))
        self.waiting_time.setValue(max(0.1, min(30.0, float(config.get("waiting_time_seconds", 5.0) or 5.0))))
        self.hold_ms.setValue(max(1, min(200, int(config.get("click_hold_ms", 24) or 24))))

    def extract_config(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled.isChecked(),
            "waiting_time_seconds": self.waiting_time.value(),
            "click_hold_ms": self.hold_ms.value(),
        }
