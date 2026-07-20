from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from app.device_service import DeviceService
from app.platform.monitor import default_monitor_geometry
from app.ui.tabs.base import BaseTab


class SharedSettingsTab(BaseTab):
    def __init__(self, device_service: DeviceService, parent=None) -> None:
        super().__init__(parent)
        self.device_service = device_service

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        shared_group = QtWidgets.QGroupBox("Shared Input / Game Settings")
        shared_layout = QtWidgets.QFormLayout(shared_group)
        shared_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        shared_layout.setHorizontalSpacing(12)
        shared_layout.setVerticalSpacing(6)

        self.shared_keyboard_device = QtWidgets.QComboBox()
        shared_layout.addRow("Keyboard device", self.shared_keyboard_device)

        self.shared_game_sensitivity = QtWidgets.QDoubleSpinBox()
        self.shared_game_sensitivity.setRange(0.01, 50.0)
        self.shared_game_sensitivity.setDecimals(4)
        self.shared_game_sensitivity.setSingleStep(0.01)
        shared_layout.addRow("Game Sensitivity", self.shared_game_sensitivity)

        self.shared_game_width = QtWidgets.QSpinBox()
        self.shared_game_width.setRange(1, 100000)
        self.shared_game_width.setSingleStep(10)
        self.shared_game_height = QtWidgets.QSpinBox()
        self.shared_game_height.setRange(1, 100000)
        self.shared_game_height.setSingleStep(10)
        resolution_row = QtWidgets.QWidget()
        resolution_layout = QtWidgets.QHBoxLayout(resolution_row)
        resolution_layout.setContentsMargins(0, 0, 0, 0)
        resolution_layout.addWidget(QtWidgets.QLabel("Width"))
        resolution_layout.addWidget(self.shared_game_width)
        resolution_layout.addWidget(QtWidgets.QLabel("Height"))
        resolution_layout.addWidget(self.shared_game_height)

        self.shared_game_stretched = QtWidgets.QCheckBox("Stretched")
        self.shared_game_stretched.setToolTip(
            "Use when the in-game resolution is stretched to the display resolution.",
        )
        resolution_layout.addWidget(self.shared_game_stretched)

        resolution_layout.addStretch(1)
        shared_layout.addRow("Game Resolution", resolution_row)

        self.shared_display_width = QtWidgets.QSpinBox()
        self.shared_display_width.setRange(1, 100000)
        self.shared_display_width.setSingleStep(10)
        self.shared_display_height = QtWidgets.QSpinBox()
        self.shared_display_height.setRange(1, 100000)
        self.shared_display_height.setSingleStep(10)
        display_resolution_row = QtWidgets.QWidget()
        display_resolution_layout = QtWidgets.QHBoxLayout(display_resolution_row)
        display_resolution_layout.setContentsMargins(0, 0, 0, 0)
        display_resolution_layout.addWidget(QtWidgets.QLabel("Width"))
        display_resolution_layout.addWidget(self.shared_display_width)
        display_resolution_layout.addWidget(QtWidgets.QLabel("Height"))
        display_resolution_layout.addWidget(self.shared_display_height)
        display_resolution_layout.addStretch(1)
        shared_layout.addRow("Display Resolution", display_resolution_row)

        shared_gsi_row = QtWidgets.QWidget()
        shared_gsi_layout = QtWidgets.QHBoxLayout(shared_gsi_row)
        shared_gsi_layout.setContentsMargins(0, 0, 0, 0)
        shared_gsi_layout.addWidget(shared_group, 1)
        layout.addWidget(shared_gsi_row)

        # Game State Integration section
        gsi_group = QtWidgets.QGroupBox("Game State Integration")
        gsi_layout = QtWidgets.QFormLayout(gsi_group)
        gsi_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        gsi_layout.setHorizontalSpacing(12)
        gsi_layout.setVerticalSpacing(6)

        self.gsi_enabled = QtWidgets.QCheckBox()
        gsi_layout.addRow("Enabled", self.gsi_enabled)

        self.gsi_host = QtWidgets.QLineEdit()
        gsi_layout.addRow("Host", self.gsi_host)

        self.gsi_port = QtWidgets.QSpinBox()
        self.gsi_port.setRange(1, 65535)
        gsi_layout.addRow("Port", self.gsi_port)

        shared_gsi_layout.addWidget(gsi_group, 1)

        hotkeys_group = QtWidgets.QGroupBox("Global Hotkeys")
        hotkeys_outer = QtWidgets.QVBoxLayout(hotkeys_group)
        hotkeys_outer.setSpacing(6)

        hotkeys_row = QtWidgets.QHBoxLayout()
        hotkeys_row.setSpacing(24)

        # Left column — existing hotkeys
        left_form = QtWidgets.QFormLayout()
        left_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        left_form.setHorizontalSpacing(12)
        left_form.setVerticalSpacing(6)

        self.hotkey_cv_trigger = QtWidgets.QLineEdit()
        left_form.addRow("CV Aim Assist toggle", self.hotkey_cv_trigger)

        self.hotkey_recoil = QtWidgets.QLineEdit()
        left_form.addRow("Recoil toggle", self.hotkey_recoil)

        self.hotkey_pixel_trigger = QtWidgets.QLineEdit()
        left_form.addRow("Pixel Trigger toggle", self.hotkey_pixel_trigger)

        self.hotkey_movement = QtWidgets.QLineEdit()
        left_form.addRow("Movement toggle", self.hotkey_movement)

        self.hotkey_stop_all = QtWidgets.QLineEdit()
        left_form.addRow("Stop All", self.hotkey_stop_all)

        hotkeys_row.addLayout(left_form)

        # Right column — overlay hotkey
        right_form = QtWidgets.QFormLayout()
        right_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        right_form.setHorizontalSpacing(12)
        right_form.setVerticalSpacing(6)

        self.hotkey_overlay = QtWidgets.QLineEdit()
        right_form.addRow("Overlay toggle", self.hotkey_overlay)

        hotkey_note = QtWidgets.QLabel("Use values like F1, F2, Ctrl+F1, or Alt+Shift+M.")
        hotkey_note.setWordWrap(True)
        hotkey_note.setStyleSheet("color: #666;")
        right_form.addRow("", hotkey_note)

        hotkeys_row.addLayout(right_form)
        hotkeys_outer.addLayout(hotkeys_row)

        layout.addWidget(hotkeys_group)

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
        pass

    def load_config(self, config: dict[str, Any]) -> None:
        # shared settings
        shared = config.get("shared", {})
        index = self.shared_keyboard_device.findData(str(shared.get("keyboard_device_path", "")))
        self.shared_keyboard_device.setCurrentIndex(index if index >= 0 else 0)
        self.shared_game_sensitivity.setValue(float(shared.get("game_sensitivity", 1.0) or 1.0))
        game_resolution = shared.get("game_resolution", {"width": 1600, "height": 1200})
        if not isinstance(game_resolution, dict):
            game_resolution = {"width": 1600, "height": 1200}
        self.shared_game_width.setValue(max(1, int(game_resolution.get("width", 1600) or 1600)))
        self.shared_game_height.setValue(max(1, int(game_resolution.get("height", 1200) or 1200)))
        self.shared_game_stretched.setChecked(bool(shared.get("game_resolution_stretched", True)))

        # Auto-detect primary monitor resolution; fall back to profile value, then 1920x1080.
        try:
            geom = default_monitor_geometry()
            display_resolution = {"width": geom.width, "height": geom.height}
        except Exception:
            display_resolution = shared.get("display_resolution")
            if not isinstance(display_resolution, dict):
                display_resolution = {"width": 1920, "height": 1080}
        self.shared_display_width.setValue(max(1, int(display_resolution.get("width", 1920) or 1920)))
        self.shared_display_height.setValue(max(1, int(display_resolution.get("height", 1080) or 1080)))

        # GSI settings
        gsi = config.get("gsi", {})
        self.gsi_enabled.setChecked(bool(gsi.get("enabled", True)))
        self.gsi_host.setText(str(gsi.get("host", "127.0.0.1")))
        self.gsi_port.setValue(int(gsi.get("port", 3000)))

        hotkeys = config.get("hotkeys", {})
        self.hotkey_cv_trigger.setText(str(hotkeys.get("cv_trigger", "F1") or "F1"))
        self.hotkey_recoil.setText(str(hotkeys.get("recoil", "F2") or "F2"))
        self.hotkey_pixel_trigger.setText(str(hotkeys.get("pixel_trigger", "F3") or "F3"))
        self.hotkey_movement.setText(str(hotkeys.get("movement", "F4") or "F4"))
        self.hotkey_stop_all.setText(str(hotkeys.get("stop_all", "F5") or "F5"))
        self.hotkey_overlay.setText(str(hotkeys.get("overlay", "Insert") or "Insert"))

    def extract_config(self) -> dict[str, Any]:
        return {
            "shared": {
                "keyboard_device_path": self.shared_keyboard_device.currentData() or "",
                "game_sensitivity": self.shared_game_sensitivity.value(),
                "game_resolution": {
                    "width": self.shared_game_width.value(),
                    "height": self.shared_game_height.value(),
                },
                "game_resolution_stretched": self.shared_game_stretched.isChecked(),
                "display_resolution": {
                    "width": self.shared_display_width.value(),
                    "height": self.shared_display_height.value(),
                },
            },
            "gsi": {
                "enabled": self.gsi_enabled.isChecked(),
                "host": self.gsi_host.text().strip() or "127.0.0.1",
                "port": self.gsi_port.value(),
            },
            "hotkeys": {
                "cv_trigger": self.hotkey_cv_trigger.text().strip() or "F1",
                "recoil": self.hotkey_recoil.text().strip() or "F2",
                "pixel_trigger": self.hotkey_pixel_trigger.text().strip() or "F3",
                "movement": self.hotkey_movement.text().strip() or "F4",
                "stop_all": self.hotkey_stop_all.text().strip() or "F5",
                "overlay": self.hotkey_overlay.text().strip() or "Insert",
            },
        }
