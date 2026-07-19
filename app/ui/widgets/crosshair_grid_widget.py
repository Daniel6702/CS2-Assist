"""Zoomed pixel grid widget for inspecting and selecting crosshair pixels."""
from __future__ import annotations

import math
from typing import Final

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from app.ui.widgets.crosshair_renderer import PixelCell


PixelMapT = list[list[PixelCell]]
PixelInfoT = dict[str, int | float | bool]


class PixelGridWidget(QWidget):
    """Zoomed pixel grid where crosshair pixels can be inspected and selected.

    The coordinate origin is the geometric centre of the image. For an even
    image size, the origin lies between four pixels, so the nearest pixel
    centres are labelled -0.5 and +0.5. For an odd image size, the origin
    passes through the centre of one pixel, which is labelled 0.
    """

    pixel_selected = Signal(int, int)
    selection_changed = Signal(set)

    _CHECKER_A: Final = QColor(200, 200, 200)
    _CHECKER_B: Final = QColor(150, 150, 150)
    _SEL_FILL: Final = QColor(0, 150, 255, 80)
    _SEL_PEN: Final = QPen(QColor(0, 150, 255), 2)
    _AXIS_PEN: Final = QPen(QColor(255, 0, 0, 128), 1)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixel_map: PixelMapT | None = None
        self._zoom = 16
        self._selected: set[tuple[int, int]] = set()
        self._w = 0
        self._h = 0
        self._center_x = 0.0
        self._center_y = 0.0
        self.setMouseTracking(True)

    # ── public API ─────────────────────────────────────────────────────

    def set_pixel_map(self, pixel_map: PixelMapT) -> None:
        self._pixel_map = pixel_map
        self._h = len(pixel_map)
        self._w = len(pixel_map[0]) if pixel_map else 0

        # Pixel coordinates below are expressed in edge coordinates. An even
        # width therefore produces an integer centre edge, while an odd width
        # produces a half-integer centre through the middle pixel.
        self._center_x = self._w / 2.0
        self._center_y = self._h / 2.0

        self._selected.clear()
        self.resize(self.sizeHint())
        self.update()

    def set_zoom(self, zoom: int) -> None:
        self._zoom = max(2, min(50, zoom))
        self.resize(self.sizeHint())
        self.update()

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom + 2)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom - 2)

    def get_zoom(self) -> int:
        return self._zoom

    def clear_selection(self) -> None:
        self._selected.clear()
        self.selection_changed.emit(set())
        self.update()

    def get_selected_pixels(self) -> set[tuple[int, int]]:
        return self._selected.copy()

    def image_dimensions(self) -> tuple[int, int]:
        return self._w, self._h

    def select_single_pixel(self, x: int, y: int) -> bool:
        if not self._pixel_map:
            return False
        if not (0 <= x < self._w and 0 <= y < self._h):
            return False

        self._selected = {(x, y)}
        self.pixel_selected.emit(x, y)
        self.selection_changed.emit(self._selected.copy())
        self.update()
        return True

    def find_closest_fully_empty_pixel(self) -> tuple[int, int] | None:
        if not self._pixel_map:
            return None

        best: tuple[float, float, float, int, int] | None = None
        best_pos: tuple[int, int] | None = None

        for y in range(self._h):
            row = self._pixel_map[y]
            for x in range(self._w):
                pixel = row[x]
                if int(pixel["a"]) != 0:
                    continue

                relative_x = self._relative_coordinate(x, self._center_x)
                relative_y = self._relative_coordinate(y, self._center_y)
                distance_sq = (relative_x * relative_x) + (relative_y * relative_y)

                # Deterministic tie-break: shortest Euclidean distance, then
                # smallest absolute y/x offset, then upper-most, then left-most.
                key = (
                    distance_sq,
                    abs(relative_y),
                    abs(relative_x),
                    y,
                    x,
                )
                if best is None or key < best:
                    best = key
                    best_pos = (x, y)

        return best_pos

    def selected_pixel_info(self) -> list[PixelInfoT]:
        if not self._pixel_map:
            return []

        result: list[PixelInfoT] = []
        for x, y in self._selected:
            if 0 <= y < self._h and 0 <= x < self._w:
                pixel = self._pixel_map[y][x]
                result.append(
                    {
                        "x": self._relative_coordinate(x, self._center_x),
                        "y": self._relative_coordinate(y, self._center_y),
                        "r": int(pixel["r"]),
                        "g": int(pixel["g"]),
                        "b": int(pixel["b"]),
                        "a": int(pixel["a"]),
                        "is_crosshair": bool(pixel["is_crosshair"]),
                    },
                )
        return result

    # ── sizing ─────────────────────────────────────────────────────────

    def sizeHint(self) -> QSize:
        width = max(1, self._w * self._zoom)
        height = max(1, self._h * self._zoom)
        return QSize(width, height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    # ── painting ───────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:  # noqa: N802
        if not self._pixel_map or self._w == 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Fill background with white so semi-transparent pixels render correctly
        painter.fillRect(self.rect(), Qt.GlobalColor.white)

        zoom = self._zoom
        grid_pen = QPen(QColor(0, 0, 0, 30), 1)

        for y in range(self._h):
            row = self._pixel_map[y]
            for x in range(self._w):
                pixel = row[x]
                rect = QRect(x * zoom, y * zoom, zoom, zoom)
                alpha = int(pixel["a"])

                if alpha > 0:
                    # Composite onto white for correct semi-transparent appearance
                    r, g, b = int(pixel["r"]), int(pixel["g"]), int(pixel["b"])
                    if alpha < 255:
                        inv = 255 - alpha
                        r = (r * alpha + 255 * inv) // 255
                        g = (g * alpha + 255 * inv) // 255
                        b = (b * alpha + 255 * inv) // 255
                    painter.fillRect(rect, QColor(r, g, b, 255))
                else:
                    painter.fillRect(
                        rect,
                        self._CHECKER_A if ((x + y) & 1) == 0 else self._CHECKER_B,
                    )

                if zoom >= 6:
                    painter.setPen(grid_pen)
                    painter.drawRect(rect)

        for selected_x, selected_y in self._selected:
            rect = QRect(selected_x * zoom, selected_y * zoom, zoom, zoom)
            painter.fillRect(rect, self._SEL_FILL)
            painter.setPen(self._SEL_PEN)
            painter.drawRect(rect)

        if zoom >= 8:
            painter.setPen(self._AXIS_PEN)
            center_x = round(self._center_x * zoom)
            center_y = round(self._center_y * zoom)
            pixel_width = self._w * zoom
            pixel_height = self._h * zoom
            painter.drawLine(center_x, 0, center_x, pixel_height)
            painter.drawLine(0, center_y, pixel_width, center_y)

        painter.end()

    # ── mouse handling ─────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._pixel_map:
            return

        x = int(event.position().x() // self._zoom)
        y = int(event.position().y() // self._zoom)
        if 0 <= y < self._h and 0 <= x < self._w:
            key = (x, y)
            if key in self._selected:
                self._selected.discard(key)
            else:
                self._selected = {key}  # single selection only

            self.pixel_selected.emit(x, y)
            self.selection_changed.emit(self._selected.copy())
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._pixel_map:
            super().mouseMoveEvent(event)
            return

        x = int(event.position().x() // self._zoom)
        y = int(event.position().y() // self._zoom)

        if 0 <= y < self._h and 0 <= x < self._w:
            pixel = self._pixel_map[y][x]
            relative_x = self._relative_coordinate(x, self._center_x)
            relative_y = self._relative_coordinate(y, self._center_y)
            self.setToolTip(
                f"Pixel ({self._format_coordinate(relative_x)}, "
                f"{self._format_coordinate(relative_y)})  |  "
                f"RGBA({pixel['r']}, {pixel['g']}, {pixel['b']}, {pixel['a']})  |  "
                f"Crosshair: {'Yes' if pixel['is_crosshair'] else 'No'}",
            )
        else:
            self.setToolTip("")

        super().mouseMoveEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            self.set_zoom(self._zoom + (2 if delta > 0 else -2))
            event.accept()
            return
        super().wheelEvent(event)

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _relative_coordinate(index: int, center_edge: float) -> float:
        return (index + 0.5) - center_edge

    @staticmethod
    def _format_coordinate(value: float) -> str:
        if math.isclose(value, round(value), abs_tol=1e-9):
            return str(int(round(value)))
        return f"{value:.1f}"
