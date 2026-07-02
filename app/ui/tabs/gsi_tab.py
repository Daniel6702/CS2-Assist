from __future__ import annotations

from typing import Any

from PySide6 import QtWidgets

from app.ui.tabs.base import BaseTab


class GSITab(BaseTab):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QtWidgets.QFormLayout(self)

        self.gsi_enabled = QtWidgets.QCheckBox()
        layout.addRow("Enabled", self.gsi_enabled)

        self.gsi_host = QtWidgets.QLineEdit()
        layout.addRow("Host", self.gsi_host)

        self.gsi_port = QtWidgets.QSpinBox()
        self.gsi_port.setRange(1, 65535)
        layout.addRow("Port", self.gsi_port)

        self.gsi_last_state = QtWidgets.QLabel("No data yet.")
        layout.addRow("Last state", self.gsi_last_state)

    def set_last_state(self, message: str) -> None:
        self.gsi_last_state.setText(message)

    def load_config(self, config: dict[str, Any]) -> None:
        self.gsi_enabled.setChecked(bool(config.get("enabled", True)))
        self.gsi_host.setText(str(config.get("host", "127.0.0.1")))
        self.gsi_port.setValue(int(config.get("port", 3000)))

    def extract_config(self) -> dict[str, Any]:
        return {
            "enabled": self.gsi_enabled.isChecked(),
            "host": self.gsi_host.text().strip() or "127.0.0.1",
            "port": self.gsi_port.value(),
        }
