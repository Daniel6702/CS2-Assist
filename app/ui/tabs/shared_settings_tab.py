from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from app.device_service import DeviceService
from app.ui.tabs.base import BaseTab


def _jitter_spin() -> QtWidgets.QDoubleSpinBox:
    w = QtWidgets.QDoubleSpinBox()
    w.setRange(0.0, 0.50)
    w.setDecimals(2)
    w.setSingleStep(0.01)
    w.setSuffix("")
    return w


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

        hotkeys_group = QtWidgets.QGroupBox("Global Hotkeys")
        hotkeys_outer = QtWidgets.QVBoxLayout(hotkeys_group)
        hotkeys_outer.setSpacing(6)

        hotkeys_row = QtWidgets.QHBoxLayout()
        hotkeys_row.setSpacing(24)

        # Left column — existing hotkeys
        left_form = QtWidgets.QFormLayout()
        left_form.setLabelAlignment(QtCore.Qt.AlignTop)
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
        right_form.setLabelAlignment(QtCore.Qt.AlignTop)
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

        # Safety & Anti-Detection section
        safety_group = QtWidgets.QGroupBox("Safety / Anti-Detection")
        safety_outer = QtWidgets.QVBoxLayout(safety_group)
        safety_outer.setSpacing(8)

        # Master toggles row
        toggles_row = QtWidgets.QHBoxLayout()
        toggles_row.setSpacing(24)
        self.safety_enabled = QtWidgets.QCheckBox("Enable safety measures")
        toggles_row.addWidget(self.safety_enabled)
        self.safety_obscure_names = QtWidgets.QCheckBox("Obscure uinput device names")
        toggles_row.addWidget(self.safety_obscure_names)
        toggles_row.addStretch(1)
        safety_outer.addLayout(toggles_row)

        # Three horizontal sub-boxes for each component
        boxes_row = QtWidgets.QHBoxLayout()
        boxes_row.setSpacing(8)

        def _make_comp_box(title: str, fields: list[tuple[str, QtWidgets.QWidget]]) -> QtWidgets.QGroupBox:
            box = QtWidgets.QGroupBox(title)
            fl = QtWidgets.QFormLayout(box)
            fl.setLabelAlignment(QtCore.Qt.AlignTop)
            fl.setHorizontalSpacing(10)
            fl.setVerticalSpacing(4)
            fl.setContentsMargins(6, 6, 6, 6)
            for label, widget in fields:
                fl.addRow(label, widget)
            return box

        # -- Recoil box
        self.safety_recoil_step = _jitter_spin()
        self.safety_recoil_noise_mix = _jitter_spin()
        self.safety_recoil_noise_decay = _jitter_spin()
        recoil_box = _make_comp_box("Recoil", [
            ("Step timing jitter", self.safety_recoil_step),
            ("Noise mix jitter", self.safety_recoil_noise_mix),
            ("Noise decay jitter", self.safety_recoil_noise_decay),
        ])
        boxes_row.addWidget(recoil_box)

        # -- Pixel Trigger box
        self.safety_pixel_cooldown = _jitter_spin()
        self.safety_pixel_click_delay = _jitter_spin()
        self.safety_pixel_poll = _jitter_spin()
        pixel_box = _make_comp_box("Pixel Trigger", [
            ("Cooldown jitter", self.safety_pixel_cooldown),
            ("Click delay jitter", self.safety_pixel_click_delay),
            ("Poll interval jitter", self.safety_pixel_poll),
        ])
        boxes_row.addWidget(pixel_box)

        # -- CV Aim Assist box
        self.safety_cv_prediction = _jitter_spin()
        self.safety_cv_sleep = _jitter_spin()
        self.safety_cv_click_hold = _jitter_spin()
        self.safety_cv_cooldown = _jitter_spin()
        self.safety_cv_eased = QtWidgets.QCheckBox()
        cv_box = _make_comp_box("CV Aim Assist", [
            ("Prediction timing jitter", self.safety_cv_prediction),
            ("Loop sleep jitter", self.safety_cv_sleep),
            ("Click hold jitter", self.safety_cv_click_hold),
            ("Cooldown jitter", self.safety_cv_cooldown),
            ("Eased movement (multi-frame)", self.safety_cv_eased),
        ])
        boxes_row.addWidget(cv_box)

        safety_outer.addLayout(boxes_row)

        safety_note = QtWidgets.QLabel(
            "All values default to 0 (disabled). Set between 0.01–0.50 to add "
            "random variance that reduces machine-perfect timing signals."
        )
        safety_note.setWordWrap(True)
        safety_note.setStyleSheet("color: #666;")
        safety_outer.addWidget(safety_note)

        layout.addWidget(safety_group)
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

        hotkeys = config.get("hotkeys", {})
        self.hotkey_cv_trigger.setText(str(hotkeys.get("cv_trigger", "F1") or "F1"))
        self.hotkey_recoil.setText(str(hotkeys.get("recoil", "F2") or "F2"))
        self.hotkey_pixel_trigger.setText(str(hotkeys.get("pixel_trigger", "F3") or "F3"))
        self.hotkey_movement.setText(str(hotkeys.get("movement", "F4") or "F4"))
        self.hotkey_stop_all.setText(str(hotkeys.get("stop_all", "F5") or "F5"))
        self.hotkey_overlay.setText(str(hotkeys.get("overlay", "Insert") or "Insert"))

        safety = config.get("safety", {})
        self.safety_enabled.setChecked(bool(safety.get("enabled", False)))
        self.safety_obscure_names.setChecked(bool(safety.get("obscure_device_names", False)))

        recoil_s = safety.get("recoil", {})
        self.safety_recoil_step.setValue(float(recoil_s.get("jitter_step_fraction", 0.0)))
        self.safety_recoil_noise_mix.setValue(float(recoil_s.get("jitter_noise_mix_fraction", 0.0)))
        self.safety_recoil_noise_decay.setValue(float(recoil_s.get("jitter_noise_decay_fraction", 0.0)))

        pixel_s = safety.get("pixel_trigger", {})
        self.safety_pixel_cooldown.setValue(float(pixel_s.get("jitter_cooldown_fraction", 0.0)))
        self.safety_pixel_click_delay.setValue(float(pixel_s.get("jitter_click_delay_fraction", 0.0)))
        self.safety_pixel_poll.setValue(float(pixel_s.get("jitter_poll_fraction", 0.0)))

        cv_s = safety.get("cv_trigger", {})
        self.safety_cv_prediction.setValue(float(cv_s.get("jitter_prediction_fraction", 0.0)))
        self.safety_cv_sleep.setValue(float(cv_s.get("jitter_sleep_fraction", 0.0)))
        self.safety_cv_click_hold.setValue(float(cv_s.get("jitter_click_hold_fraction", 0.0)))
        self.safety_cv_cooldown.setValue(float(cv_s.get("jitter_cooldown_fraction", 0.0)))
        self.safety_cv_eased.setChecked(bool(cv_s.get("eased_movement_enabled", False)))

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
            "hotkeys": {
                "cv_trigger": self.hotkey_cv_trigger.text().strip() or "F1",
                "recoil": self.hotkey_recoil.text().strip() or "F2",
                "pixel_trigger": self.hotkey_pixel_trigger.text().strip() or "F3",
                "movement": self.hotkey_movement.text().strip() or "F4",
                "stop_all": self.hotkey_stop_all.text().strip() or "F5",
                "overlay": self.hotkey_overlay.text().strip() or "Insert",
            },
            "safety": {
                "enabled": self.safety_enabled.isChecked(),
                "obscure_device_names": self.safety_obscure_names.isChecked(),
                "recoil": {
                    "jitter_step_fraction": self.safety_recoil_step.value(),
                    "jitter_noise_mix_fraction": self.safety_recoil_noise_mix.value(),
                    "jitter_noise_decay_fraction": self.safety_recoil_noise_decay.value(),
                },
                "pixel_trigger": {
                    "jitter_cooldown_fraction": self.safety_pixel_cooldown.value(),
                    "jitter_click_delay_fraction": self.safety_pixel_click_delay.value(),
                    "jitter_poll_fraction": self.safety_pixel_poll.value(),
                },
                "cv_trigger": {
                    "jitter_prediction_fraction": self.safety_cv_prediction.value(),
                    "jitter_sleep_fraction": self.safety_cv_sleep.value(),
                    "jitter_click_hold_fraction": self.safety_cv_click_hold.value(),
                    "jitter_cooldown_fraction": self.safety_cv_cooldown.value(),
                    "eased_movement_enabled": self.safety_cv_eased.isChecked(),
                },
            },
        }
