from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from .curve_model import clamp_sort_points, ensure_endpoints


class CurveCanvas(QtWidgets.QWidget):
    changed = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._points: list[tuple[float, float]] = [(0.0, 0.0), (1.0, 1.0)]
        self._selected_index = -1
        self._dragging_index = -1
        self._margin = 20
        self._hit_radius = 10.0
        self._editable = True
        self.setMinimumHeight(260)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    def points(self) -> list[tuple[float, float]]:
        return list(self._points)

    def selected_index(self) -> int:
        return self._selected_index

    def editable(self) -> bool:
        return self._editable

    def set_editable(self, editable: bool) -> None:
        self._editable = editable
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor if editable else QtCore.Qt.CursorShape.ForbiddenCursor)

    def set_points(self, points: list[tuple[float, float]]) -> None:
        self._points = ensure_endpoints(clamp_sort_points(points))
        self._selected_index = min(self._selected_index, len(self._points) - 1)
        self.update()

    def add_point(self, point: tuple[float, float]) -> int:
        if not self._editable:
            return -1
        self._points = ensure_endpoints(clamp_sort_points([*self._points, point]))
        inserted = min(range(len(self._points)), key=lambda idx: abs(self._points[idx][0] - point[0]))
        self._selected_index = inserted
        self.update()
        self.changed.emit()
        return inserted

    def remove_selected_point(self) -> bool:
        if not self._editable:
            return False
        if self._selected_index <= 0 or self._selected_index >= len(self._points) - 1:
            return False
        del self._points[self._selected_index]
        self._selected_index = min(self._selected_index, len(self._points) - 1)
        self.update()
        self.changed.emit()
        return True

    def plot_rect(self) -> QtCore.QRectF:
        margin = float(self._margin)
        rect = QtCore.QRectF(self.rect())
        return rect.adjusted(margin, margin, -margin, -margin)

    def point_to_pos(self, point: tuple[float, float]) -> QtCore.QPointF:
        plot = self.plot_rect()
        x = plot.left() + point[0] * plot.width()
        y = plot.bottom() - point[1] * plot.height()
        return QtCore.QPointF(x, y)

    def pos_to_point(self, pos: QtCore.QPointF) -> tuple[float, float]:
        plot = self.plot_rect()
        if plot.width() <= 0.0 or plot.height() <= 0.0:
            return (0.0, 0.0)
        x = (pos.x() - plot.left()) / plot.width()
        y = (plot.bottom() - pos.y()) / plot.height()
        return (max(0.0, min(1.0, x)), max(0.0, min(1.0, y)))

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self._draw_background(painter)
        self._draw_curve(painter)
        self._draw_points(painter)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if not self._editable:
            super().mousePressEvent(event)
            return
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            self._remove_right_clicked_point(event.position())
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self.setFocus()
        pos = event.position()
        hit = self._hit_index(pos)
        if hit >= 0:
            self._selected_index = hit
            self._dragging_index = hit
        else:
            self._dragging_index = self.add_point(self.pos_to_point(pos))
        self.update()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._dragging_index < 0:
            super().mouseMoveEvent(event)
            return
        self._move_point(self._dragging_index, self.pos_to_point(event.position()))

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._dragging_index = -1
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Backspace):
            if self.remove_selected_point():
                return
        super().keyPressEvent(event)

    def _move_point(self, index: int, point: tuple[float, float]) -> None:
        if not self._editable:
            return
        x, y = point
        if index == 0:
            point = (0.0, y)
        elif index == len(self._points) - 1:
            point = (1.0, y)
        else:
            previous_x = self._points[index - 1][0] + 0.001
            next_x = self._points[index + 1][0] - 0.001
            point = (max(previous_x, min(next_x, x)), y)
        self._points[index] = point
        self._selected_index = index
        self.update()
        self.changed.emit()

    def _remove_right_clicked_point(self, pos: QtCore.QPointF) -> None:
        hit = self._hit_index(pos)
        if hit != self._selected_index:
            return
        self.remove_selected_point()

    def _hit_index(self, pos: QtCore.QPointF) -> int:
        for index, point in enumerate(self._points):
            if QtCore.QLineF(pos, self.point_to_pos(point)).length() <= self._hit_radius:
                return index
        return -1

    def _draw_background(self, painter: QtGui.QPainter) -> None:
        plot = self.plot_rect()
        palette = self.palette()
        painter.fillRect(self.rect(), palette.color(QtGui.QPalette.ColorRole.Base))
        painter.setPen(QtGui.QPen(palette.color(QtGui.QPalette.ColorRole.Mid), 1))
        for step in range(6):
            ratio = step / 5.0
            x = plot.left() + ratio * plot.width()
            y = plot.top() + ratio * plot.height()
            painter.drawLine(QtCore.QPointF(x, plot.top()), QtCore.QPointF(x, plot.bottom()))
            painter.drawLine(QtCore.QPointF(plot.left(), y), QtCore.QPointF(plot.right(), y))
        painter.setPen(QtGui.QPen(palette.color(QtGui.QPalette.ColorRole.Text), 1))
        painter.drawRect(plot)

    def _draw_curve(self, painter: QtGui.QPainter) -> None:
        if len(self._points) < 2:
            return
        path = QtGui.QPainterPath(self.point_to_pos(self._points[0]))
        for start, end in zip(self._points, self._points[1:]):
            start_pos = self.point_to_pos(start)
            end_pos = self.point_to_pos(end)
            dx = (end_pos.x() - start_pos.x()) * 0.5
            path.cubicTo(
                QtCore.QPointF(start_pos.x() + dx, start_pos.y()),
                QtCore.QPointF(end_pos.x() - dx, end_pos.y()),
                end_pos,
            )
        painter.setPen(QtGui.QPen(self.palette().color(QtGui.QPalette.ColorRole.Highlight), 2))
        painter.drawPath(path)

    def _draw_points(self, painter: QtGui.QPainter) -> None:
        palette = self.palette()
        for index, point in enumerate(self._points):
            pos = self.point_to_pos(point)
            radius = 5.0 if index != self._selected_index else 7.0
            color_role = QtGui.QPalette.ColorRole.Highlight if index == self._selected_index else QtGui.QPalette.ColorRole.Button
            painter.setBrush(QtGui.QBrush(palette.color(color_role)))
            painter.setPen(QtGui.QPen(palette.color(QtGui.QPalette.ColorRole.Text), 1))
            painter.drawEllipse(pos, radius, radius)
