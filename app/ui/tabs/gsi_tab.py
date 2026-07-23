from __future__ import annotations

from typing import Any

from PySide6 import QtWidgets

from app.ui.tabs.base import BaseTab
from app.ui.widgets.gsi_controls import GSIControlsWidget


class GSITab(BaseTab):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        self.gsi_controls = GSIControlsWidget()
        self.gsi_host = self.gsi_controls.host
        self.gsi_port = self.gsi_controls.port
        self.gsi_system_mode = self.gsi_controls.system_mode
        self.gsi_connection_status = self.gsi_controls.connection_status
        self.gsi_system_status = self.gsi_controls.system_status
        layout.addWidget(self.gsi_controls)

    def set_last_state(self, message: str) -> None:
        return

    def set_gsi_connection_status(self, connected: bool) -> None:
        self.gsi_controls.set_connection_status(connected)

    def set_gsi_system_active(self, active: bool) -> None:
        self.gsi_controls.set_system_active(active)

    def set_gsi_system_mode(self, mode: str) -> None:
        self.gsi_controls.set_system_mode(mode)

    def gsi_system_mode_value(self) -> str:
        return self.gsi_controls.system_mode_value()

    def load_config(self, config: dict[str, Any]) -> None:
        self.gsi_controls.load_config(config)

    def extract_config(self) -> dict[str, Any]:
        return self.gsi_controls.extract_config()
