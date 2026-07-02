from __future__ import annotations

import sys

from PySide6 import QtWidgets

from app.ui.main_window import MainWindow
from app.ui.styles import apply_style


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    apply_style(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
