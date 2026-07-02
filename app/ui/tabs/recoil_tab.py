from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from app.device_service import DeviceService
from app.ui.tabs.base import BaseTab, load_widget_class
from app.ui.widgets import ComponentEditor


class RecoilTab(BaseTab):
    config_changed = QtCore.Signal(str, dict)

    def __init__(self, device_service: DeviceService, parent=None) -> None:
        super().__init__(parent)
        ComponentEditor = load_widget_class("ComponentEditor")

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        content = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(content)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(12)

        # Three horizontal group boxes side by side
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(12)

        # Base Controls
        base_group = QtWidgets.QGroupBox("Base Controls")
        base_layout = QtWidgets.QFormLayout(base_group)
        base_layout.setLabelAlignment(QtCore.Qt.AlignTop)
        base_layout.setHorizontalSpacing(12)
        base_layout.setVerticalSpacing(6)

        # Mouse Return
        return_group = QtWidgets.QGroupBox("Mouse Return")
        return_layout = QtWidgets.QFormLayout(return_group)
        return_layout.setLabelAlignment(QtCore.Qt.AlignTop)
        return_layout.setHorizontalSpacing(12)
        return_layout.setVerticalSpacing(6)

        # Bullet Overlay
        overlay_group = QtWidgets.QGroupBox("Bullet Overlay")
        overlay_layout = QtWidgets.QFormLayout(overlay_group)
        overlay_layout.setLabelAlignment(QtCore.Qt.AlignTop)
        overlay_layout.setHorizontalSpacing(12)
        overlay_layout.setVerticalSpacing(6)

        # Build the editors with only their respective fields
        self.base_editor = ComponentEditor(
            "recoil_base",
            "",
            [
                {"path": "enabled", "label": "Enabled", "kind": "bool"},
                {"path": "axis_strength_percent.x", "label": "X strength %", "kind": "float", "min": 0.0, "max": 300.0, "step": 1.0},
                {"path": "axis_strength_percent.y", "label": "Y strength %", "kind": "float", "min": 0.0, "max": 300.0, "step": 1.0},
                {"path": "movement.frequency_hz", "label": "Update frequency (Hz)", "kind": "int", "min": 30, "max": 1000},
                {"path": "movement.max_delta_per_event", "label": "Max delta per event (px)", "kind": "int", "min": 0, "max": 50},
                {"path": "noise.strength_px", "label": "Noise amount (px)", "kind": "float", "min": 0.0, "max": 5.0, "step": 0.01, "decimals": 3},
            ],
            device_service=device_service,
        )

        self.return_editor = ComponentEditor(
            "recoil_return",
            "",
            [
                {"path": "return_mouse.enabled", "label": "Return mouse after spray", "kind": "bool"},
                {"path": "return_mouse.delay_ms", "label": "Return delay (ms)", "kind": "int", "min": 0, "max": 500},
                {"path": "return_mouse.duration_ms", "label": "Return duration (ms)", "kind": "int", "min": 20, "max": 1000},
                {"path": "return_mouse.y_percent", "label": "Return Y %", "kind": "float", "min": 0.0, "max": 100.0, "step": 1.0, "decimals": 1, "default": 100.0},
            ],
            device_service=device_service,
        )

        self.overlay_editor = ComponentEditor(
            "recoil_overlay",
            "",
            [
                {"path": "overlay.enabled", "label": "Show bullet overlay", "kind": "bool"},
                {"path": "overlay.screen_scale", "label": "Spray / overlay scale", "kind": "float", "min": 0.01, "max": 2.0, "step": 0.01, "decimals": 3},
                {"path": "overlay.diameter_px", "label": "Overlay size (px)", "kind": "int", "min": 4, "max": 64},
                {"path": "overlay.opacity", "label": "Overlay opacity", "kind": "float", "min": 0.05, "max": 1.0, "step": 0.05, "decimals": 2},
                {"path": "overlay.color", "label": "Overlay color", "kind": "color"},
            ],
            device_service=device_service,
        )

        # Add editors to their group boxes
        for editor, layout in [
            (self.base_editor, base_layout),
            (self.return_editor, return_layout),
            (self.overlay_editor, overlay_layout),
        ]:
            editor.setTitle("")
            layout.addWidget(editor)

        # First row: Base Controls and Mouse Return side by side
        top_row = QtWidgets.QHBoxLayout()
        top_row.setSpacing(12)
        top_row.addWidget(base_group, 1)
        top_row.addWidget(return_group, 1)

        # Second row: Bullet Overlay spans full width
        bottom_row = QtWidgets.QHBoxLayout()
        bottom_row.addWidget(overlay_group, 1)

        main_layout.addLayout(top_row)
        main_layout.addLayout(bottom_row)
        main_layout.addStretch(1)

        scroll.setWidget(content)

        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll)

        # Connect signals
        for editor in (self.base_editor, self.return_editor, self.overlay_editor):
            editor.config_changed.connect(self._on_config_changed)

    def _on_config_changed(self, component_name: str, config: dict[str, Any]) -> None:
        # Merge configs from all three editors and emit combined signal
        combined = {}
        for editor in (self.base_editor, self.return_editor, self.overlay_editor):
            combined.update(editor.extract_config())
        self.config_changed.emit("recoil", combined)

    def load_config(self, config: dict[str, Any]) -> None:
        for editor in (self.base_editor, self.return_editor, self.overlay_editor):
            editor.load_config(config)

    def extract_config(self) -> dict[str, Any]:
        combined = {}
        for editor in (self.base_editor, self.return_editor, self.overlay_editor):
            combined.update(editor.extract_config())
        return combined

    def refresh_devices(self) -> None:
        for editor in (self.base_editor, self.return_editor, self.overlay_editor):
            editor.refresh_devices()

    def set_runtime_status(self, message: str) -> None:
        for editor in (self.base_editor, self.return_editor, self.overlay_editor):
            editor.set_runtime_status(message)