from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from app.device_service import DeviceService
from app.ui.tabs.base import BaseTab


class SharedSettingsTab(BaseTab):
    def __init__(self, device_service: DeviceService, parent=None) -> None:
        super().__init__(parent)
        self.device_service = device_service

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        # Shared Input / Sensitivity section
        shared_group = QtWidgets.QGroupBox("Shared Input / Sensitivity")
        shared_layout = QtWidgets.QFormLayout(shared_group)
        shared_layout.setLabelAlignment(QtCore.Qt.AlignTop)
        shared_layout.setHorizontalSpacing(12)
        shared_layout.setVerticalSpacing(6)

        self.shared_keyboard_device = QtWidgets.QComboBox()
        shared_layout.addRow("Keyboard device", self.shared_keyboard_device)

        self.shared_game_sensitivity = QtWidgets.QDoubleSpinBox()
        self.shared_game_sensitivity.setRange(0.01, 50.0)
        self.shared_game_sensitivity.setDecimals(4)
        self.shared_game_sensitivity.setSingleStep(0.01)
        shared_layout.addRow("Game / program sensitivity", self.shared_game_sensitivity)

        note = QtWidgets.QLabel(
            "Used by keyboard-based features for the selected input device, and by recoil / CV trigger for sensitivity scaling."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        shared_layout.addRow("", note)

        layout.addWidget(shared_group)

        # Game State Integration section
        gsi_group = QtWidgets.QGroupBox("Game State Integration")
        gsi_layout = QtWidgets.QFormLayout(gsi_group)
        gsi_layout.setLabelAlignment(QtCore.Qt.AlignTop)
        gsi_layout.setHorizontalSpacing(12)
        gsi_layout.setVerticalSpacing(6)

        self.gsi_enabled = QtWidgets.QCheckBox()
        gsi_layout.addRow("Enabled", self.gsi_enabled)

        self.gsi_host = QtWidgets.QLineEdit()
        gsi_layout.addRow("Host", self.gsi_host)

        self.gsi_port = QtWidgets.QSpinBox()
        self.gsi_port.setRange(1, 65535)
        gsi_layout.addRow("Port", self.gsi_port)

        self.gsi_last_state = QtWidgets.QLabel("No data yet.")
        gsi_layout.addRow("Last state", self.gsi_last_state)

        layout.addWidget(gsi_group)
        layout.addStretch(1)

    def refresh_devices(self) -> None:
        current = self.shared_keyboard_device.currentData()
        self.shared_keyboard_device.blockSignals(True)
        self.shared_keyboard_device.clear()
        self.shared_keyboard_device.addItem("Auto-detect", "")
        for item in self.device_service.list_keyboards():
            self.shared_keyboard_device.addItem(item.label, item.path)
        index = self.shared_keyboard_device.findData(current)
        if index >= 0:
            self.shared_keyboard_device.setCurrentIndex(index)
        self.shared_keyboard_device.blockSignals(False)

    def set_last_state(self, message: str) -> None:
        self.gsi_last_state.setText(message)

    def load_config(self, config: dict[str, Any]) -> None:
        # shared settings
        shared = config.get("shared", {})
        index = self.shared_keyboard_device.findData(str(shared.get("keyboard_device_path", "")))
        self.shared_keyboard_device.setCurrentIndex(index if index >= 0 else 0)
        self.shared_game_sensitivity.setValue(float(shared.get("game_sensitivity", 1.0) or 1.0))

        # GSI settings
        gsi = config.get("gsi", {})
        self.gsi_enabled.setChecked(bool(gsi.get("enabled", True)))
        self.gsi_host.setText(str(gsi.get("host", "127.0.0.1")))
        self.gsi_port.setValue(int(gsi.get("port", 3000)))

    def extract_config(self) -> dict[str, Any]:
        return {
            "shared": {
                "keyboard_device_path": self.shared_keyboard_device.currentData() or "",
                "game_sensitivity": self.shared_game_sensitivity.value(),
            },
            "gsi": {
                "enabled": self.gsi_enabled.isChecked(),
                "host": self.gsi_host.text().strip() or "127.0.0.1",
                "port": self.gsi_port.value(),
            },
        }