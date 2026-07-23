from __future__ import annotations

from typing import Any

from PySide6 import QtWidgets

from app.ui.tabs.base import BaseTab


_ACTIVE_STATUS_STYLE = "color: #4ade80;"
_INACTIVE_STATUS_STYLE = "color: #ef4444;"


class GSITab(BaseTab):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QtWidgets.QFormLayout(self)

        self.gsi_host = QtWidgets.QLineEdit()
        layout.addRow("Host", self.gsi_host)

        self.gsi_port = QtWidgets.QSpinBox()
        self.gsi_port.setRange(1, 65535)
        layout.addRow("Port", self.gsi_port)

        self.gsi_connection_status = QtWidgets.QLabel("Waiting for connection ...")
        layout.addRow("Status", self.gsi_connection_status)

        self.gsi_system_status = QtWidgets.QLabel("Inactive")
        self.gsi_system_status.setStyleSheet(_INACTIVE_STATUS_STYLE)
        layout.addRow("System", self.gsi_system_status)

    def set_last_state(self, message: str) -> None:
        return

    def set_gsi_connection_status(self, connected: bool) -> None:
        self.gsi_connection_status.setText("Connected" if connected else "Waiting for connection ...")

    def set_gsi_system_active(self, active: bool) -> None:
        self.gsi_system_status.setText("Active" if active else "Inactive")
        self.gsi_system_status.setStyleSheet(_ACTIVE_STATUS_STYLE if active else _INACTIVE_STATUS_STYLE)

    def load_config(self, config: dict[str, Any]) -> None:
        self.gsi_host.setText(str(config.get("host", "127.0.0.1")))
        self.gsi_port.setValue(int(config.get("port", 3000)))
        self.set_gsi_connection_status(False)
        self.set_gsi_system_active(False)

    def extract_config(self) -> dict[str, Any]:
        return {
            "host": self.gsi_host.text().strip() or "127.0.0.1",
            "port": self.gsi_port.value(),
        }
