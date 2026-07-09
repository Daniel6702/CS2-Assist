from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class BulletImpactOverlay(QtWidgets.QWidget):
    """Recoil bullet-impact dot overlay.

    The widget is shown once at init and *never hidden*.  The circular
    mask is applied **once** (never toggled) so the X11 Shape extension
    doesn't cause round-trip lag.  When inactive the dot sits in the
    top-left corner — always on-screen, always alive in the compositor.
    """

    def __init__(self) -> None:
        super().__init__(None)
        self._diameter: int = 12
        self._opacity: float = 0.9

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

        self.setFixedSize(self._diameter, self._diameter)
        self.setMask(
            QtGui.QRegion(0, 0, self._diameter, self._diameter, QtGui.QRegion.RegionType.Ellipse)
        )
        self.move(0, 0)

        self._raise_timer = QtCore.QTimer(self)
        self._raise_timer.timeout.connect(self._keep_on_top)
        self._raise_timer.start(250)

        self.show()

    def configure(
        self,
        diameter_px: int,
        opacity: float,
        monitor_geometry: tuple[int, int, int, int] | None = None,
    ) -> None:
        diameter_px = max(4, int(diameter_px))
        opacity = max(0.05, min(1.0, float(opacity)))
        changed = diameter_px != self._diameter
        self._diameter = diameter_px
        self._opacity = opacity
        if changed:
            self.setFixedSize(self._diameter, self._diameter)
            self.setMask(
                QtGui.QRegion(0, 0, self._diameter, self._diameter, QtGui.QRegion.RegionType.Ellipse)
            )
            self.update()

    def _keep_on_top(self) -> None:
        self.raise_()

    def show_point(self, center_x: float, center_y: float) -> None:
        x = int(round(center_x - self._diameter / 2))
        y = int(round(center_y - self._diameter / 2))
        self.move(x, y)
        self.raise_()
        self.update()

    def hide_overlay(self) -> None:
        self.move(0, 0)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QtCore.Qt.NoPen)
        alpha = max(1, min(255, int(round(self._opacity * 255))))
        painter.setBrush(QtGui.QColor(255, 0, 0, alpha))
        painter.drawEllipse(0, 0, self._diameter, self._diameter)
