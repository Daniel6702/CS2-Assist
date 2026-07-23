from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from app.device_service import DeviceService
from app.platform.monitor import default_monitor_geometry
from app.ui.tabs.base import BaseTab
from app.ui.widgets.gsi_controls import GSIControlsWidget


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


class SharedSettingsTab(BaseTab):
    change_game_directory_requested = QtCore.Signal()

    def __init__(self, device_service: DeviceService, parent=None) -> None:
        super().__init__(parent)
        self.device_service = device_service

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        # ===== Two-column layout =====
        columns = QtWidgets.QHBoxLayout()
        columns.setSpacing(12)

        # ---- LEFT COLUMN ----
        left_column = QtWidgets.QVBoxLayout()
        left_column.setSpacing(12)

        # --- CS2 Assist box ---
        cs2_assist_group = QtWidgets.QGroupBox("CS2 Assist")
        cs2_assist_layout = QtWidgets.QFormLayout(cs2_assist_group)
        cs2_assist_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        cs2_assist_layout.setHorizontalSpacing(12)
        cs2_assist_layout.setVerticalSpacing(8)

        self.gsi_system_mode = QtWidgets.QButtonGroup(self)
        self.gsi_system_mode.setExclusive(True)
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
            self.gsi_system_mode.addButton(button, mode_id)
            system_mode_layout.addWidget(button)
        system_mode_layout.addStretch(1)
        cs2_assist_layout.addRow("Switch", system_mode_row)

        self.gsi_system_status = QtWidgets.QLabel("Inactive")
        self.gsi_system_status.setStyleSheet(_INACTIVE_STATUS_STYLE)
        cs2_assist_layout.addRow("System", self.gsi_system_status)

        left_column.addWidget(cs2_assist_group)

        # --- Game State Integration box (connection info only) ---
        self.gsi_controls = GSIControlsWidget(show_system_mode=False)
        self.gsi_host = self.gsi_controls.host
        self.gsi_port = self.gsi_controls.port
        self.gsi_connection_status = self.gsi_controls.connection_status

        left_column.addWidget(self.gsi_controls)

        columns.addLayout(left_column, 1)

        # ---- RIGHT COLUMN ----
        right_column = QtWidgets.QVBoxLayout()
        right_column.setSpacing(12)

        # --- Shared Input / Game Settings box ---
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

        self.change_game_directory_btn = QtWidgets.QPushButton("Change Game Directory...")
        self.change_game_directory_btn.setToolTip("Select a different Counter-Strike 2 game folder and reinstall cfg files.")
        self.change_game_directory_btn.clicked.connect(self.change_game_directory_requested)
        shared_layout.addRow("CS2 Directory", self.change_game_directory_btn)

        right_column.addWidget(shared_group)
        right_column.addStretch(1)

        columns.addLayout(right_column, 1)

        layout.addLayout(columns)

        # ===== Global Hotkeys (full width below columns) =====
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

    def set_gsi_connection_status(self, connected: bool) -> None:
        self.gsi_controls.set_connection_status(connected)

    def set_gsi_system_active(self, active: bool) -> None:
        self.gsi_system_status.setText("Active" if active else "Inactive")
        self.gsi_system_status.setStyleSheet(_ACTIVE_STATUS_STYLE if active else _INACTIVE_STATUS_STYLE)

    def set_gsi_system_mode(self, mode: str) -> None:
        normalized = mode.strip().lower()
        for mode_id, (_, value) in enumerate(_SYSTEM_MODE_ITEMS):
            if value == normalized:
                button = self.gsi_system_mode.button(mode_id)
                if button is not None:
                    button.setChecked(True)
                return
        fallback = self.gsi_system_mode.button(2)
        if fallback is not None:
            fallback.setChecked(True)

    def gsi_system_mode_value(self) -> str:
        checked_id = self.gsi_system_mode.checkedId()
        if 0 <= checked_id < len(_SYSTEM_MODE_ITEMS):
            return _SYSTEM_MODE_ITEMS[checked_id][1]
        return "gsi"

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
        self.gsi_controls.load_config(gsi if isinstance(gsi, dict) else {})
        # System mode is handled by the CS2 Assist box
        if isinstance(gsi, dict):
            self.set_gsi_system_mode(str(gsi.get("mode", "gsi")))
        self.set_gsi_system_active(False)

        hotkeys = config.get("hotkeys", {})
        self.hotkey_cv_trigger.setText(str(hotkeys.get("cv_trigger", "F1") or "F1"))
        self.hotkey_recoil.setText(str(hotkeys.get("recoil", "F2") or "F2"))
        self.hotkey_pixel_trigger.setText(str(hotkeys.get("pixel_trigger", "F3") or "F3"))
        self.hotkey_movement.setText(str(hotkeys.get("movement", "F4") or "F4"))
        self.hotkey_stop_all.setText(str(hotkeys.get("stop_all", "F5") or "F5"))
        self.hotkey_overlay.setText(str(hotkeys.get("overlay", "Insert") or "Insert"))

    def extract_config(self) -> dict[str, Any]:
        gsi = self.gsi_controls.extract_config()
        gsi["mode"] = self.gsi_system_mode_value()
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
            "gsi": gsi,
            "hotkeys": {
                "cv_trigger": self.hotkey_cv_trigger.text().strip() or "F1",
                "recoil": self.hotkey_recoil.text().strip() or "F2",
                "pixel_trigger": self.hotkey_pixel_trigger.text().strip() or "F3",
                "movement": self.hotkey_movement.text().strip() or "F4",
                "stop_all": self.hotkey_stop_all.text().strip() or "F5",
                "overlay": self.hotkey_overlay.text().strip() or "Insert",
            },
        }
