from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from app.platform.monitor import default_monitor_geometry


class _BaseOverlay(QtWidgets.QWidget):
    """Small fixed-size frameless overlay."""

    def __init__(self, width: int, height: int) -> None:
        super().__init__(None)
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
        self.setFixedSize(width, height)
        self.move(0, 0)

        self._raise_timer = QtCore.QTimer(self)
        self._raise_timer.timeout.connect(self._keep_on_top)
        self._raise_timer.start(250)

        self.setVisible(False)

    def _keep_on_top(self) -> None:
        if self.isVisible():
            self.raise_()

    def _move_to(self, x: int, y: int) -> None:
        self.setVisible(True)
        self.raise_()
        self.move(x, y)
        self.update()

    def hide_overlay(self) -> None:
        self.setVisible(False)


class BombTimerOverlay:
    """Manages two small overlay widgets — countdown + warning cross.

    Provides the same update_state() interface as before so MainWindow
    doesn't need to change.
    """

    def __init__(self) -> None:
        self._text_widget: _CountdownOverlay | None = None
        self._cross_widget: _CrossOverlay | None = None
        self._last_font_size = 48
        self._create_text_widget(48)
        self._cross_widget = _CrossOverlay()

    def _create_text_widget(self, font_size: int) -> None:
        if self._text_widget is not None:
            self._text_widget.hide_overlay()
            self._text_widget.close()
            self._text_widget.deleteLater()
        self._text_widget = _CountdownOverlay(font_size)
        self._last_font_size = font_size

    def update_state(
        self,
        bomb_active: bool,
        remaining: int,
        show_warning: bool,
        font_size: int,
        color: QtGui.QColor | tuple[int, int, int] | str,
    ) -> None:
        # Recreate text widget if font size changed
        font_size = max(12, int(font_size))
        if font_size != self._last_font_size:
            self._create_text_widget(font_size)

        if isinstance(color, QtGui.QColor):
            qcolor = color
        elif isinstance(color, str):
            qcolor = QtGui.QColor(color)
        elif isinstance(color, tuple):
            qcolor = QtGui.QColor(*color)
        else:
            qcolor = QtGui.QColor(255, 50, 50)

        # Countdown
        if bomb_active and remaining > 0:
            mon = default_monitor_geometry()
            x = 40
            y = (mon.height - self._text_widget.height()) // 2
            self._text_widget._move_to(x, y)
            self._text_widget.update_content(str(remaining), qcolor)
        else:
            self._text_widget.hide_overlay()

        # Warning cross
        if show_warning:
            mon = default_monitor_geometry()
            cx = mon.width // 2 - self._cross_widget.width() // 2
            cy = mon.height // 2 - 80 - self._cross_widget.height() // 2
            self._cross_widget._move_to(cx, cy)
        else:
            self._cross_widget.hide_overlay()


class _CountdownOverlay(_BaseOverlay):
    """Shows the bomb timer countdown text."""

    def __init__(self, font_size: int) -> None:
        # Size for the widest text ("40") at this font size
        font = QtGui.QFont("monospace", font_size)
        font.setBold(True)
        metrics = QtGui.QFontMetrics(font)
        w = metrics.horizontalAdvance("40") + 20
        h = metrics.height() + 10
        super().__init__(w, h)

        self._font = font
        self._text = ""
        self._color = QtGui.QColor(255, 50, 50)

    def _update_mask(self) -> None:
        if not self._text:
            return
        # Per-pixel alpha mask from rendered text — no rect background.
        img = QtGui.QImage(self.size(), QtGui.QImage.Format_ARGB32_Premultiplied)
        img.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(img)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setFont(self._font)
        p.setPen(QtCore.Qt.white)
        p.drawText(img.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()
        mask = QtGui.QBitmap.fromImage(img.createAlphaMask())
        self.setMask(QtGui.QRegion(mask))

    def update_content(self, text: str, color: QtGui.QColor) -> None:
        self._text = text
        self._color = color
        self._update_mask()
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setFont(self._font)
        painter.setPen(self._color)
        painter.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, self._text)


class _CrossOverlay(_BaseOverlay):
    """Semi-transparent red cross above the crosshair."""

    def __init__(self) -> None:
        super().__init__(30, 30)
        self._update_mask()

    def _update_mask(self) -> None:
        img = QtGui.QImage(30, 30, QtGui.QImage.Format_ARGB32_Premultiplied)
        img.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(img)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtCore.Qt.white)
        cx = 15
        cy = 15
        p.drawRect(cx - 12, cy - 2, 24, 5)
        p.drawRect(cx - 2, cy - 12, 5, 24)
        p.end()
        self.setMask(QtGui.QRegion(QtGui.QBitmap.fromImage(img.createAlphaMask())))

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(255, 0, 0, 120))

        cx = self.width() // 2
        cy = self.height() // 2
        painter.drawRect(cx - 12, cy - 2, 24, 5)
        painter.drawRect(cx - 2, cy - 12, 5, 24)
