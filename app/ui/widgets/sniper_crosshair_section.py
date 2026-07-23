from __future__ import annotations

import re
from typing import Any

from PySide6 import QtCore, QtWidgets

from app.ui.widgets.crosshair_codec import CS2CrosshairCodec


_CODE_PATTERN = re.compile(r"^CSGO(-[ABCDEFGHJKLMNOPQRSTUVWXYZabcdefhijkmnopqrstuvwxyz23456789]{5}){5}$")


def _normalize_crosshair_code(code: str) -> str:
    normalized = code.strip()
    if not normalized or normalized.startswith("CSGO-"):
        return normalized
    raw = normalized.replace("-", "")
    if len(raw) != 25:
        return normalized
    return "CSGO-{}-{}-{}-{}-{}".format(raw[:5], raw[5:10], raw[10:15], raw[15:20], raw[20:])


def _canonical_crosshair_code(code: str) -> str:
    normalized = _normalize_crosshair_code(code)
    if not normalized:
        return ""
    if _CODE_PATTERN.fullmatch(normalized) is None:
        return normalized
    codec = CS2CrosshairCodec()
    return codec.generate_code(codec.parse_code(normalized))


class SniperCrosshairSection(QtWidgets.QGroupBox):
    changed = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Sniper Crosshair", parent)
        self.setStyleSheet("QGroupBox { font-weight: 600; }")
        form = QtWidgets.QFormLayout(self)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.enabled = QtWidgets.QCheckBox()
        self.enabled.stateChanged.connect(self.changed)
        form.addRow("Enabled", self.enabled)

        self.stay_when_scoped = QtWidgets.QCheckBox()
        self.stay_when_scoped.stateChanged.connect(self.changed)
        form.addRow("Stay When Scoped", self.stay_when_scoped)

        self.crosshair_code = QtWidgets.QLineEdit()
        self.crosshair_code.setPlaceholderText("Blank uses Pixel Trigger crosshair code")
        self.crosshair_code.editingFinished.connect(self._on_code_edited)
        code_row = QtWidgets.QHBoxLayout()
        code_row.addWidget(self.crosshair_code, 1)
        parse_button = QtWidgets.QPushButton("Parse")
        parse_button.clicked.connect(self._on_code_edited)
        code_row.addWidget(parse_button)
        form.addRow("Crosshair code", code_row)

    def load_config(self, config: dict[str, Any]) -> None:
        self.enabled.setChecked(bool(config.get("enabled", False)))
        self.stay_when_scoped.setChecked(bool(config.get("stay_when_scoped", False)))
        self.crosshair_code.setText(str(config.get("crosshair_code", "") or ""))
        self._update_code_style()

    def extract_config(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled.isChecked(),
            "crosshair_code": _canonical_crosshair_code(self.crosshair_code.text()),
            "stay_when_scoped": self.stay_when_scoped.isChecked(),
        }

    def _on_code_edited(self) -> None:
        self.crosshair_code.setText(_canonical_crosshair_code(self.crosshair_code.text()))
        self._update_code_style()
        self.changed.emit()

    def _update_code_style(self) -> None:
        code = self.crosshair_code.text().strip()
        valid = not code or _CODE_PATTERN.fullmatch(_normalize_crosshair_code(code)) is not None
        self.crosshair_code.setStyleSheet("" if valid else "border: 1px solid #B00020;")
