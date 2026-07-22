from __future__ import annotations

from typing import Any

from .curve_model import (
    CurveDict,
    clamp_sort_points,
    ensure_endpoints,
    extract_curves,
    id_from_label,
    load_curves,
    normalize_curve,
    unique_id,
)


# ---------------------------------------------------------------------------
# AimCurveEditor widget  (requires PySide6)
# ---------------------------------------------------------------------------

try:
    from PySide6 import QtCore, QtWidgets

    from .curve_canvas import CurveCanvas

    class AimCurveEditor(QtWidgets.QWidget):
        """Curve library editor widget."""

        changed = QtCore.Signal()

        def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
            super().__init__(parent)
            self._curves: dict[str, CurveDict] = {}
            self._current_id: str = ""

            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)

            top_row = QtWidgets.QHBoxLayout()
            top_row.addWidget(QtWidgets.QLabel("Curve:"))
            self.curve_combo = QtWidgets.QComboBox()
            self.curve_combo.currentIndexChanged.connect(self._on_combo_changed)
            top_row.addWidget(self.curve_combo, 1)

            top_row.addWidget(QtWidgets.QLabel("Name:"))
            self.name_edit = QtWidgets.QLineEdit()
            self.name_edit.setPlaceholderText("Curve name")
            self.name_edit.editingFinished.connect(self._on_rename)
            top_row.addWidget(self.name_edit, 1)
            layout.addLayout(top_row)

            # -- preset buttons (inline) --
            btn_row = QtWidgets.QHBoxLayout()
            self.add_btn = QtWidgets.QPushButton("+ Add")
            self.add_btn.clicked.connect(self._on_add)
            btn_row.addWidget(self.add_btn)

            self.copy_btn = QtWidgets.QPushButton("Copy")
            self.copy_btn.clicked.connect(self._on_copy)
            btn_row.addWidget(self.copy_btn)

            self.remove_btn = QtWidgets.QPushButton("Remove")
            self.remove_btn.clicked.connect(self._on_remove)
            btn_row.addWidget(self.remove_btn)

            self.rename_btn = QtWidgets.QPushButton("Rename")
            self.rename_btn.clicked.connect(self._on_rename)
            btn_row.addWidget(self.rename_btn)
            layout.addLayout(btn_row)

            self.canvas = CurveCanvas()
            self.canvas.changed.connect(self._on_canvas_changed)
            layout.addWidget(self.canvas)

            self._rebuild_combo()

        # -- public API ---------------------------------------------------

        def load_curves(self, curves: dict[str, CurveDict]) -> None:
            """Replace internal curve library and rebuild the selector."""
            self._curves = dict(curves)
            if self._current_id not in self._curves:
                self._current_id = next(iter(self._curves), "")
            self._rebuild_combo()
            self._sync_name_field()
            self._sync_canvas()
            self._emit_changed()

        def extract_curves(self) -> dict[str, dict[str, Any]]:
            """Return profile-safe serializable dict of all curves."""
            return extract_curves(self._curves)

        def add_curve(self, label: str, points: list[tuple[float, float]]) -> str:
            """Add a new curve, return its id.  Selects it in the combo."""
            cid = unique_id(label, set(self._curves))
            norm = normalize_curve({"label": label, "points": points})
            if norm is None:
                norm = {"label": label, "points": [(0.0, 0.0), (1.0, 1.0)]}
            norm["_id"] = cid
            self._curves[cid] = norm
            self._current_id = cid
            self._rebuild_combo(select=cid)
            self._sync_name_field()
            self._sync_canvas()
            self._emit_changed()
            return cid

        def copy_current_curve(self, new_label: str = "") -> str:
            """Duplicate the currently selected curve, return the new id."""
            src = self._current_curve()
            if src is None:
                return ""
            base_label = new_label or (src.get("label", "Copy") + " Copy")
            points = list(src["points"])
            return self.add_curve(base_label, points)

        def remove_current_curve(self) -> None:
            """Remove the currently selected curve, if more than one remains."""
            if len(self._curves) <= 1 or not self._current_id:
                return
            del self._curves[self._current_id]
            self._current_id = next(iter(self._curves), "")
            self._rebuild_combo(select=self._current_id)
            self._sync_name_field()
            self._sync_canvas()
            self._emit_changed()

        def rename_current_curve(self, new_label: str) -> None:
            """Rename the currently selected curve."""
            cd = self._current_curve()
            if cd is None:
                return
            new_id = unique_id(new_label, set(self._curves) - {self._current_id})
            cd["label"] = new_label
            # if id changed (label-based), remap
            if new_id != self._current_id:
                self._curves[new_id] = cd
                del self._curves[self._current_id]
                self._current_id = new_id
            self._rebuild_combo(select=self._current_id)
            self._sync_name_field()
            self._sync_canvas()
            self._emit_changed()

        def set_current_points(self, points: list[tuple[float, float]]) -> None:
            """Replace the point data of the current curve."""
            cd = self._current_curve()
            if cd is None:
                return
            sorted_points = clamp_sort_points(points)
            cd["points"] = ensure_endpoints(sorted_points)
            self._sync_canvas()
            self._emit_changed()

        def curve_count(self) -> int:
            return len(self._curves)

        def current_curve_id(self) -> str:
            return self._current_id

        def current_curve_points(self) -> list[tuple[float, float]]:
            cd = self._current_curve()
            return list(cd["points"]) if cd is not None else []

        # -- internal helpers ---------------------------------------------

        def _current_curve(self) -> CurveDict | None:
            return self._curves.get(self._current_id)

        def _rebuild_combo(self, select: str = "") -> None:
            self.curve_combo.blockSignals(True)
            self.curve_combo.clear()
            for cid, cd in self._curves.items():
                label = cd.get("label", cid)
                self.curve_combo.addItem(label, cid)
            target = select or self._current_id
            idx = self.curve_combo.findData(target)
            if idx >= 0:
                self.curve_combo.setCurrentIndex(idx)
            self.curve_combo.blockSignals(False)
            self._update_button_states()

        def _sync_name_field(self) -> None:
            cd = self._current_curve()
            self.name_edit.setText(cd.get("label", "") if cd else "")

        def _sync_canvas(self) -> None:
            cd = self._current_curve()
            self.canvas.blockSignals(True)
            self.canvas.set_points(list(cd["points"]) if cd is not None else [])
            self.canvas.set_editable(True)
            self.canvas.blockSignals(False)

        def _update_button_states(self) -> None:
            has_curves = len(self._curves) > 0
            more_than_one = len(self._curves) > 1
            self.remove_btn.setEnabled(has_curves and more_than_one)
            self.copy_btn.setEnabled(has_curves)
            self.rename_btn.setEnabled(has_curves)

        def _on_combo_changed(self, index: int) -> None:
            cid = self.curve_combo.itemData(index)
            if cid is not None and cid in self._curves:
                self._current_id = str(cid)
                self._sync_name_field()
                self._sync_canvas()
                self._update_button_states()

        def _on_add(self) -> None:
            self.add_curve("New Curve", [(0.0, 0.0), (1.0, 1.0)])

        def _on_copy(self) -> None:
            self.copy_current_curve()

        def _on_remove(self) -> None:
            self.remove_current_curve()

        def _on_rename(self) -> None:
            label = self.name_edit.text().strip()
            if label:
                self.rename_current_curve(label)

        def _emit_changed(self) -> None:
            self.changed.emit()

        def _on_canvas_changed(self) -> None:
            cd = self._current_curve()
            if cd is None:
                return
            cd["points"] = self.canvas.points()
            self._emit_changed()

except ImportError:

    class AimCurveEditor:  # type: ignore[no-redef]
        """Stub when PySide6 is not available."""

        changed = None  # would be Signal if PySide6 were present

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def load_curves(self, curves: dict[str, CurveDict]) -> None:
            pass

        def extract_curves(self) -> dict[str, dict[str, Any]]:
            return {}

        def add_curve(self, label: str, points: list[tuple[float, float]]) -> str:
            return ""

        def copy_current_curve(self, new_label: str = "") -> str:
            return ""

        def remove_current_curve(self) -> None:
            pass

        def rename_current_curve(self, new_label: str) -> None:
            pass

        def set_current_points(self, points: list[tuple[float, float]]) -> None:
            pass

        def curve_count(self) -> int:
            return 0

        def current_curve_id(self) -> str:
            return ""

        def current_curve_points(self) -> list[tuple[float, float]]:
            return []

        def template_points(self, template_id: str) -> list[tuple[float, float]]:
            return []
