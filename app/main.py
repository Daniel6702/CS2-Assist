from __future__ import annotations

import sys

from PySide6 import QtWidgets

from app.ui import MainWindow


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
