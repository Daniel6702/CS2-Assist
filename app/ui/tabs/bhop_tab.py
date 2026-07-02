from __future__ import annotations

from typing import Any

from PySide6 import QtWidgets

from app.device_service import DeviceService
from app.ui.schemas import component_schemas
from app.ui.tabs.base import BaseTab, load_widget_class


class BhopTab(BaseTab):
    def __init__(self, device_service: DeviceService, parent=None) -> None:
        super().__init__(parent)
        ComponentEditor = load_widget_class("ComponentEditor")
        layout = QtWidgets.QVBoxLayout(self)
        self.editor = ComponentEditor("bhop", "Bhop", _schema_for("bhop"), device_service=device_service)
        layout.addWidget(self.editor)

    def load_config(self, config: dict[str, Any]) -> None:
        self.editor.load_config(config)

    def extract_config(self) -> dict[str, Any]:
        return self.editor.extract_config()

    def refresh_devices(self) -> None:
        self.editor.refresh_devices()

    def set_runtime_status(self, message: str) -> None:
        self.editor.set_runtime_status(message)


def _schema_for(component_name: str) -> list[dict[str, Any]]:
    for name, _title, schema in component_schemas():
        if name == component_name:
            return schema
    return []
