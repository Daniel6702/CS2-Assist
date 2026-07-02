from __future__ import annotations

from PySide6 import QtCore


class LogBridge(QtCore.QObject):
    message = QtCore.Signal(str, str)
