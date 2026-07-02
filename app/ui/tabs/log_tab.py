from __future__ import annotations

from typing import Any

from PySide6 import QtWidgets

from app.ui.tabs.base import BaseTab


class LogTab(BaseTab):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        layout.addWidget(self.log)

    def append_log(self, source: str, message: str) -> None:
        self.log.appendPlainText(f"{source}: {message}")

    def clear_log(self) -> None:
        self.log.clear()

    def load_config(self, config: dict[str, Any]) -> None:
        pass

    def extract_config(self) -> dict[str, Any]:
        return {}