from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class BulletImpactOverlay(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__(None)
        self._diameter = 12
        self._opacity = 0.9

        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.X11BypassWindowManagerHint
            | QtCore.Qt.WindowTransparentForInput
            | QtCore.Qt.WindowDoesNotAcceptFocus
            | QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self._apply_shape()

        self._raise_timer = QtCore.QTimer(self)
        self._raise_timer.timeout.connect(self._keep_on_top)
        self._raise_timer.start(250)

        self.hide()

    def _apply_shape(self) -> None:
        self.setFixedSize(self._diameter, self._diameter)
        self.setMask(QtGui.QRegion(0, 0, self._diameter, self._diameter, QtGui.QRegion.RegionType.Ellipse))

    def configure(self, diameter_px: int, opacity: float) -> None:
        diameter_px = max(4, int(diameter_px))
        opacity = max(0.05, min(1.0, float(opacity)))
        changed = diameter_px != self._diameter
        self._diameter = diameter_px
        self._opacity = opacity
        if changed:
            self._apply_shape()
            self.update()

    def _keep_on_top(self) -> None:
        if self.isVisible():
            self.raise_()

    def show_point(self, center_x: float, center_y: float) -> None:
        x = int(round(center_x - self._diameter / 2))
        y = int(round(center_y - self._diameter / 2))
        self.move(x, y)
        if not self.isVisible():
            self.show()
        self.raise_()
        self.update()

    def hide_overlay(self) -> None:
        self.hide()

    def paintEvent(self, event) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QtCore.Qt.NoPen)
        alpha = max(1, min(255, int(round(self._opacity * 255))))
        painter.setBrush(QtGui.QColor(255, 0, 0, alpha))
        painter.drawEllipse(0, 0, self._diameter, self._diameter)
