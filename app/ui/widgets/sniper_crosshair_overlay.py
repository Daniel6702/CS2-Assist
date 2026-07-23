from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from app.components.sniper_crosshair import SNIPER_CROSSHAIR_STRETCH_FILTER, SniperCrosshairOverlayState
from app.platform.monitor import default_monitor_geometry
from app.ui.widgets.crosshair_codec import CS2CrosshairCodec
from app.ui.widgets.crosshair_renderer import CrosshairRenderer


class SniperCrosshairOverlay(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__(None)
        self._codec = CS2CrosshairCodec()
        self._renderer = CrosshairRenderer()
        self._image = QtGui.QImage()
        self._last_render_key: tuple[str, int, int, int, int, bool] | None = None

        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.X11BypassWindowManagerHint
            | QtCore.Qt.WindowType.WindowTransparentForInput
            | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus
            | QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setVisible(False)

        self._raise_timer = QtCore.QTimer(self)
        self._raise_timer.timeout.connect(self._keep_on_top)
        self._raise_timer.start(250)

    def update_state(self, state: SniperCrosshairOverlayState) -> None:
        if not state.visible:
            self.hide_overlay()
            return
        self._render(state)
        if self._image.isNull():
            self.hide_overlay()
            return
        monitor = default_monitor_geometry()
        x = monitor.left + (monitor.width - self._image.width()) // 2
        y = monitor.top + (monitor.height - self._image.height()) // 2
        self.setVisible(True)
        self.raise_()
        self.move(x, y)
        self.update()

    def hide_overlay(self) -> None:
        self.setVisible(False)

    def _render(self, state: SniperCrosshairOverlayState) -> None:
        render_key = (
            state.crosshair_code,
            state.game_width,
            state.game_height,
            state.display_width,
            state.display_height,
            state.stretched,
        )
        if render_key == self._last_render_key:
            return
        settings = self._codec.parse_code(state.crosshair_code)
        self._image = self._renderer.render_for_resolution(
            settings,
            state.game_width,
            state.game_height,
            stretch_to_display=state.stretched,
            display_width=state.display_width,
            display_height=state.display_height,
            stretch_filter=SNIPER_CROSSHAIR_STRETCH_FILTER,
        )
        self._last_render_key = render_key
        self.setFixedSize(self._image.width(), self._image.height())
        self.setMask(QtGui.QRegion(QtGui.QBitmap.fromImage(self._image.createAlphaMask())))

    def _keep_on_top(self) -> None:
        if self.isVisible():
            self.raise_()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.drawImage(0, 0, self._image)
