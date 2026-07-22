from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets


class AutoShootSection(QtWidgets.QGroupBox):
    changed = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Auto Shoot", parent)
        self.setStyleSheet("QGroupBox { font-weight: 600; }")
        form = QtWidgets.QFormLayout(self)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.enabled = QtWidgets.QCheckBox()
        self.enabled.stateChanged.connect(self.changed)
        form.addRow("Enabled", self.enabled)

        self.cps = QtWidgets.QDoubleSpinBox()
        self.cps.setRange(0.1, 100.0)
        self.cps.setSingleStep(0.5)
        self.cps.setDecimals(1)
        self.cps.setValue(8.0)
        self.cps.setSuffix(" cps")
        self.cps.valueChanged.connect(self.changed)
        form.addRow("Click rate", self.cps)

        self.hold_ms = QtWidgets.QSpinBox()
        self.hold_ms.setRange(1, 200)
        self.hold_ms.setValue(20)
        self.hold_ms.setSuffix(" ms")
        self.hold_ms.valueChanged.connect(self.changed)
        form.addRow("Click hold", self.hold_ms)

        file_row = QtWidgets.QHBoxLayout()
        self.weapon_file = QtWidgets.QLineEdit()
        self.weapon_file.setPlaceholderText("./resources/weapons_data/semi-auto_weapon_codes.txt")
        self.weapon_file.editingFinished.connect(self.changed)
        file_row.addWidget(self.weapon_file, 1)
        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        file_row.addWidget(browse_btn)
        form.addRow("Weapon codes", file_row)

    def load_config(self, config: dict[str, Any]) -> None:
        self.enabled.setChecked(bool(config.get("enabled", False)))
        self.cps.setValue(max(0.1, min(100.0, float(config.get("clicks_per_second", 8.0) or 8.0))))
        self.hold_ms.setValue(max(1, min(200, int(config.get("click_hold_ms", 20) or 20))))
        self.weapon_file.setText(
            str(config.get("allowed_weapon_file", "./resources/weapons_data/semi-auto_weapon_codes.txt") or "./resources/weapons_data/semi-auto_weapon_codes.txt")
        )

    def extract_config(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled.isChecked(),
            "clicks_per_second": self.cps.value(),
            "click_hold_ms": self.hold_ms.value(),
            "allowed_weapon_file": self.weapon_file.text().strip() or "./resources/weapons_data/semi-auto_weapon_codes.txt",
        }

    def _browse(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Auto Shoot Weapon Codes",
            "",
            "Text Files (*.txt);;All Files (*)",
        )
        if path:
            self.weapon_file.setText(path)
            self.changed.emit()
