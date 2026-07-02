from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from app.device_service import DeviceService
from app.ui.schemas import component_schemas
from app.ui.tabs.base import BaseTab, load_widget_class


class RecoilTab(BaseTab):
    def __init__(self, device_service: DeviceService, parent=None) -> None:
        super().__init__(parent)
        ComponentEditor = load_widget_class("ComponentEditor")
        
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        
        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 4, 4)
        
        self.editor = ComponentEditor("recoil", "Recoil Control", _schema_for("recoil"), device_service=device_service)
        layout.addWidget(self.editor)
        layout.addStretch(1)
        
        scroll.setWidget(content)
        
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

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
