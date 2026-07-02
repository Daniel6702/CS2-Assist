from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from app.device_service import DeviceService
from app.ui.schemas import component_schemas
from app.ui.tabs.base import BaseTab, load_widget_class


WidgetClass = load_widget_class("ComponentEditor")


def _schema_for(component_name: str) -> list[dict[str, Any]]:
    for name, _title, schema in component_schemas():
        if name == component_name:
            return schema
    return []


class _ComponentSection(QtWidgets.QWidget):
    def __init__(self, name: str, title: str, schema: list[dict[str, Any]], device_service: DeviceService, parent=None) -> None:
        super().__init__(parent)
        self.name = name
        self.editor = WidgetClass(name, title, schema, device_service=device_service)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.editor)

    def load_config(self, config: dict[str, Any]) -> None:
        self.editor.load_config(config)

    def extract_config(self) -> dict[str, Any]:
        return self.editor.extract_config()

    def refresh_devices(self) -> None:
        self.editor.refresh_devices()

    def set_runtime_status(self, message: str) -> None:
        self.editor.set_runtime_status(message)


class MovementTab(BaseTab):
    def __init__(self, device_service: DeviceService, parent=None) -> None:
        super().__init__(parent)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        self.sections = {
            "bhop": _ComponentSection("bhop", "Bhop", _schema_for("bhop"), device_service),
            "snap_tap": _ComponentSection("snap_tap", "Snap Tap / Null Binds", _schema_for("snap_tap"), device_service),
            "counter_strafe": _ComponentSection("counter_strafe", "Counter Strafe", _schema_for("counter_strafe"), device_service),
        }

        for section in self.sections.values():
            layout.addWidget(section)

        layout.addStretch(1)

        scroll.setWidget(content)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def load_config(self, config: dict[str, Any]) -> None:
        for name, section in self.sections.items():
            section.load_config(config.get(name, {}))

    def extract_config(self) -> dict[str, Any]:
        return {name: section.extract_config() for name, section in self.sections.items()}

    def refresh_devices(self) -> None:
        for section in self.sections.values():
            section.refresh_devices()

    def set_runtime_status(self, message: str) -> None:
        for section in self.sections.values():
            section.set_runtime_status(message)

    def get_section(self, name: str) -> _ComponentSection | None:
        return self.sections.get(name)