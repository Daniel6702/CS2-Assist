from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets


_ACTIVE_STATUS_STYLE = "color: #4ade80; font-weight: 600;"
_INACTIVE_STATUS_STYLE = "color: #ef4444; font-weight: 600;"
_SYSTEM_MODE_ITEMS = (("On", "on"), ("Off", "off"), ("GSI", "gsi"))
_SWITCH_ROW_STYLE = "QWidget#gsiSystemModeRow { background-color: #252526; border: none; }"

_MODE_BUTTON_STYLE = """
QPushButton {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    color: #d4d4d4;
    padding: 7px 14px;
}
QPushButton:hover:!checked {
    background-color: #2d2d30;
    border-color: #505050;
    color: #ffffff;
}
QPushButton[segment_position="left"] {
    border-top-left-radius: 6px;
    border-bottom-left-radius: 6px;
    border-right-width: 0;
}
QPushButton[segment_position="middle"] {
    border-radius: 0;
    border-right-width: 0;
}
QPushButton[segment_position="right"] {
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}
QPushButton[system_mode="on"]:checked {
    background-color: #14532d;
    border-color: #22c55e;
    color: #ffffff;
}
QPushButton[system_mode="off"]:checked {
    background-color: #7f1d1d;
    border-color: #ef4444;
    color: #ffffff;
}
QPushButton[system_mode="gsi"]:checked {
    background-color: #0f3b5f;
    border-color: #38bdf8;
    color: #ffffff;
}
"""


class GSIControlsWidget(QtWidgets.QGroupBox):
    def __init__(self, parent: QtWidgets.QWidget | None = None, show_system_mode: bool = True) -> None:
        super().__init__("Game State Integration", parent)
        self._show_system_mode = show_system_mode

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(10)

        connection_form = QtWidgets.QFormLayout()
        connection_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        connection_form.setHorizontalSpacing(12)
        connection_form.setVerticalSpacing(6)

        self.host = QtWidgets.QLineEdit()
        connection_form.addRow("Host", self.host)

        self.port = QtWidgets.QSpinBox()
        self.port.setRange(1, 65535)
        connection_form.addRow("Port", self.port)

        self.connection_status = QtWidgets.QLabel("Waiting for connection ...")
        connection_form.addRow("Status", self.connection_status)
        layout.addLayout(connection_form)

        if self._show_system_mode:
            separator = QtWidgets.QWidget()
            separator.setFixedHeight(1)
            separator.setStyleSheet("background-color: #3c3c3c; border: none;")
            layout.addWidget(separator)

            system_form = QtWidgets.QFormLayout()
            system_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
            system_form.setHorizontalSpacing(12)
            system_form.setVerticalSpacing(8)

            self.system_mode = QtWidgets.QButtonGroup(self)
            self.system_mode.setExclusive(True)
            system_mode_row = QtWidgets.QWidget()
            system_mode_row.setObjectName("gsiSystemModeRow")
            system_mode_row.setStyleSheet(_SWITCH_ROW_STYLE)
            system_mode_layout = QtWidgets.QHBoxLayout(system_mode_row)
            system_mode_layout.setContentsMargins(0, 2, 0, 0)
            system_mode_layout.setSpacing(0)
            positions = ("left", "middle", "right")
            for mode_id, (label, mode) in enumerate(_SYSTEM_MODE_ITEMS):
                button = QtWidgets.QPushButton(label)
                button.setCheckable(True)
                button.setMinimumWidth(64)
                button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
                button.setProperty("system_mode", mode)
                button.setProperty("segment_position", positions[mode_id])
                button.setStyleSheet(_MODE_BUTTON_STYLE)
                self.system_mode.addButton(button, mode_id)
                system_mode_layout.addWidget(button)
            system_mode_layout.addStretch(1)
            system_form.addRow("Switch", system_mode_row)

            self.system_status = QtWidgets.QLabel("Inactive")
            self.system_status.setStyleSheet(_INACTIVE_STATUS_STYLE)
            system_form.addRow("System", self.system_status)
            layout.addLayout(system_form)

    def set_connection_status(self, connected: bool) -> None:
        self.connection_status.setText("Connected" if connected else "Waiting for connection ...")

    def set_system_active(self, active: bool) -> None:
        self.system_status.setText("Active" if active else "Inactive")
        self.system_status.setStyleSheet(_ACTIVE_STATUS_STYLE if active else _INACTIVE_STATUS_STYLE)

    def set_system_mode(self, mode: str) -> None:
        normalized = mode.strip().lower()
        for mode_id, (_, value) in enumerate(_SYSTEM_MODE_ITEMS):
            if value == normalized:
                button = self.system_mode.button(mode_id)
                if button is not None:
                    button.setChecked(True)
                return
        fallback = self.system_mode.button(2)
        if fallback is not None:
            fallback.setChecked(True)

    def system_mode_value(self) -> str:
        checked_id = self.system_mode.checkedId()
        if 0 <= checked_id < len(_SYSTEM_MODE_ITEMS):
            return _SYSTEM_MODE_ITEMS[checked_id][1]
        return "gsi"

    def load_config(self, config: dict[str, Any]) -> None:
        self.host.setText(str(config.get("host", "127.0.0.1")))
        self.port.setValue(int(config.get("port", 3000)))
        if self._show_system_mode:
            self.set_system_mode(str(config.get("mode", "gsi")))
            self.set_system_active(False)
        self.set_connection_status(False)

    def extract_config(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "host": self.host.text().strip() or "127.0.0.1",
            "port": self.port.value(),
        }
        if self._show_system_mode:
            result["mode"] = self.system_mode_value()
        return result
