"""Tests for app.ui.widgets.curve_editor — pure helpers + AimCurveEditor widget.

Pure helper tests never require PySide6.  Widget tests gracefully skip when
PySide6 is unavailable.
"""

from __future__ import annotations

import unittest
from pathlib import Path
import subprocess
import sys
import textwrap
from typing import Any

from app.ui.widgets.curve_editor import (
    TEMPLATES,
    CurveDict,
    clamp_sort_points,
    ensure_endpoints,
    extract_curves,
    id_from_label,
    load_curves,
    normalize_curve,
    unique_id,
)

# *********************************************************************
# Section 1 — Pure helper tests (no GUI dependency)
# *********************************************************************


class ClampSortPointsTests(unittest.TestCase):
    def test_sorts_by_x(self) -> None:
        result = clamp_sort_points([(1.0, 1.0), (0.0, 0.0), (0.5, 0.5)])
        self.assertEqual(result, [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)])

    def test_clamps_x_below_0(self) -> None:
        result = clamp_sort_points([(-0.5, 0.5), (1.0, 1.0)])
        self.assertAlmostEqual(result[0][0], 0.0)

    def test_clamps_x_above_1(self) -> None:
        result = clamp_sort_points([(0.0, 0.0), (1.5, 0.5)])
        self.assertAlmostEqual(result[-1][0], 1.0)

    def test_clamps_y_below_0(self) -> None:
        result = clamp_sort_points([(0.0, -0.2), (1.0, 1.0)])
        self.assertAlmostEqual(result[0][1], 0.0)

    def test_clamps_y_above_1(self) -> None:
        result = clamp_sort_points([(0.0, 0.0), (1.0, 1.5)])
        self.assertAlmostEqual(result[-1][1], 1.0)

    def test_accepts_ints(self) -> None:
        result = clamp_sort_points([(0, 0), (1, 1)])
        self.assertEqual(result, [(0.0, 0.0), (1.0, 1.0)])

    def test_preserves_valid_points(self) -> None:
        points = [(0.0, 0.2), (0.5, 0.5), (1.0, 0.8)]
        result = clamp_sort_points(points)
        self.assertEqual(result, points)


class EnsureEndpointsTests(unittest.TestCase):
    def test_adds_start_endpoint(self) -> None:
        result = ensure_endpoints([(0.3, 0.3), (1.0, 1.0)])
        self.assertAlmostEqual(result[0][0], 0.0)
        self.assertAlmostEqual(result[0][1], 0.3)

    def test_adds_end_endpoint(self) -> None:
        result = ensure_endpoints([(0.0, 0.0), (0.7, 0.7)])
        self.assertAlmostEqual(result[-1][0], 1.0)
        self.assertAlmostEqual(result[-1][1], 0.7)

    def test_adds_both_endpoints(self) -> None:
        result = ensure_endpoints([(0.3, 0.3), (0.7, 0.7)])
        self.assertAlmostEqual(result[0][0], 0.0)
        self.assertAlmostEqual(result[-1][0], 1.0)

    def test_empty_input_returns_default(self) -> None:
        result = ensure_endpoints([])
        self.assertEqual(result, [(0.0, 0.0), (1.0, 1.0)])

    def test_already_has_endpoints(self) -> None:
        points = [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)]
        result = ensure_endpoints(points)
        self.assertEqual(result, points)


class IdFromLabelTests(unittest.TestCase):
    def test_basic_label(self) -> None:
        self.assertEqual(id_from_label("Constant 50%"), "constant_50")

    def test_special_chars(self) -> None:
        self.assertEqual(id_from_label("My Curve!"), "my_curve")

    def test_whitespace(self) -> None:
        self.assertEqual(id_from_label("  Linear   "), "linear")

    def test_empty_string(self) -> None:
        self.assertEqual(id_from_label(""), "unnamed")

    def test_numbers_and_dots(self) -> None:
        self.assertEqual(id_from_label("Exponential 2.5"), "exponential_2_5")


class UniqueIdTests(unittest.TestCase):
    def test_no_conflict(self) -> None:
        self.assertEqual(unique_id("Constant 50%", {"linear", "exponential"}), "constant_50")

    def test_first_conflict(self) -> None:
        self.assertEqual(unique_id("Linear", {"linear"}), "linear_2")

    def test_multiple_conflicts(self) -> None:
        self.assertEqual(unique_id("Linear", {"linear", "linear_2"}), "linear_3")

    def test_empty_existing(self) -> None:
        self.assertEqual(unique_id("My Curve", set()), "my_curve")


class NormalizeCurveTests(unittest.TestCase):
    def test_dict_form(self) -> None:
        raw = {"label": "Test", "points": [[0, 0], [0.5, 0.5], [1, 1]]}
        result = normalize_curve(raw)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["label"], "Test")
        self.assertEqual(len(result["points"]), 3)

    def test_list_form(self) -> None:
        raw = [[0, 0], [1, 1]]
        result = normalize_curve(raw, fallback_label="MyList")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["label"], "MyList")
        self.assertEqual(len(result["points"]), 2)

    def test_list_form_no_fallback_label(self) -> None:
        raw = [[0, 0], [1, 1]]
        result = normalize_curve(raw)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["label"], "")

    def test_malformed_not_dict_or_list(self) -> None:
        self.assertIsNone(normalize_curve("not a curve"))

    def test_malformed_none(self) -> None:
        self.assertIsNone(normalize_curve(None))

    def test_malformed_single_point(self) -> None:
        self.assertIsNone(normalize_curve([[0, 0]]))

    def test_malformed_bad_point_type(self) -> None:
        self.assertIsNone(normalize_curve({"label": "x", "points": [[0, 0], "abc"]}))

    def test_malformed_non_numeric(self) -> None:
        self.assertIsNone(normalize_curve({"label": "x", "points": [[0, 0], ["a", "b"]]}))

    def test_malformed_empty_points(self) -> None:
        self.assertIsNone(normalize_curve({"label": "x", "points": []}))

    def test_endpoints_ensured(self) -> None:
        raw = {"label": "No ends", "points": [[0.3, 0.3], [0.7, 0.7]]}
        result = normalize_curve(raw)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertAlmostEqual(result["points"][0][0], 0.0)
        self.assertAlmostEqual(result["points"][-1][0], 1.0)

    def test_y_values_clamped(self) -> None:
        raw = {"label": "Clamp", "points": [[0, -5], [1, 5]]}
        result = normalize_curve(raw)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertAlmostEqual(result["points"][0][1], 0.0)
        self.assertAlmostEqual(result["points"][-1][1], 1.0)


class LoadCurvesTests(unittest.TestCase):
    def test_load_valid_dict(self) -> None:
        raw = {
            "my_curve": {"label": "My Curve", "points": [[0, 0], [1, 1]]},
        }
        result = load_curves(raw)
        self.assertIn("my_curve", result)
        self.assertEqual(result["my_curve"]["label"], "My Curve")

    def test_empty_input_uses_templates(self) -> None:
        result = load_curves({})
        self.assertGreaterEqual(len(result), 3)
        for key in TEMPLATES:
            self.assertIn(key, result)

    def test_non_dict_input_uses_templates(self) -> None:
        result = load_curves(None)
        self.assertGreaterEqual(len(result), 3)

    def test_invalid_entries_dropped(self) -> None:
        raw = {
            "good": {"label": "Good", "points": [[0, 0], [1, 1]]},
            "bad": "not a curve",
            "empty": {"label": "Empty", "points": []},
        }
        result = load_curves(raw)
        self.assertIn("good", result)
        self.assertNotIn("bad", result)
        self.assertNotIn("empty", result)

    def test_all_invalid_falls_back_to_templates(self) -> None:
        result = load_curves({"bad": "nope", "worse": None})
        for key in TEMPLATES:
            self.assertIn(key, result)

    def test_internal_id_tagged(self) -> None:
        raw = {"lin": {"label": "Linear", "points": [[0, 0], [1, 1]]}}
        result = load_curves(raw)
        self.assertEqual(result["lin"].get("_id"), "lin")


class ExtractCurvesTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        internal = load_curves(TEMPLATES)  # type: ignore[arg-type]
        exported = extract_curves(internal)
        self.assertEqual(set(exported.keys()), set(TEMPLATES.keys()))
        for cid, cd in exported.items():
            self.assertIn("label", cd)
            self.assertIn("points", cd)
            self.assertIsInstance(cd["label"], str)
            self.assertIsInstance(cd["points"], list)
            # Ensure _id is stripped
            self.assertNotIn("_id", cd)

    def test_values_are_plain_lists_not_tuples(self) -> None:
        internal = load_curves(TEMPLATES)  # type: ignore[arg-type]
        exported = extract_curves(internal)
        for cd in exported.values():
            for pt in cd["points"]:
                self.assertIsInstance(pt, list)
                self.assertEqual(len(pt), 2)

    def test_empty_curves(self) -> None:
        self.assertEqual(extract_curves({}), {})


class TemplatesTests(unittest.TestCase):
    def test_constant_50_structure(self) -> None:
        tpl = TEMPLATES.get("constant_50")
        self.assertIsNotNone(tpl)
        assert tpl is not None
        self.assertEqual(tpl["label"], "Constant 50%")
        self.assertEqual(len(tpl["points"]), 2)
        self.assertAlmostEqual(tpl["points"][0][1], 0.5)
        self.assertAlmostEqual(tpl["points"][1][1], 0.5)

    def test_linear_structure(self) -> None:
        tpl = TEMPLATES.get("linear")
        self.assertIsNotNone(tpl)
        assert tpl is not None
        self.assertEqual(tpl["label"], "Linear")
        self.assertGreater(len(tpl["points"]), 2)
        for x, y in tpl["points"]:
            self.assertAlmostEqual(x, y)

    def test_exponential_structure(self) -> None:
        tpl = TEMPLATES.get("exponential")
        self.assertIsNotNone(tpl)
        assert tpl is not None
        self.assertEqual(tpl["label"], "Exponential")
        self.assertGreater(len(tpl["points"]), 2)

    def test_all_templates_have_endpoints(self) -> None:
        for tid, tpl in TEMPLATES.items():
            with self.subTest(template=tid):
                pts = tpl["points"]
                self.assertAlmostEqual(pts[0][0], 0.0, msg=f"{tid} missing x=0 start")
                self.assertAlmostEqual(pts[-1][0], 1.0, msg=f"{tid} missing x=1 end")

    def test_templates_are_immutable_copies_not_reused(self) -> None:
        """Each load should produce independent copies (dict immutability
        isn't enforced, but we check that TEMPLATES themselves are not
        accidentally mutated through load_curves)."""
        before_keys = set(TEMPLATES.keys())
        _ = load_curves({"extra": {"label": "Extra", "points": [[0, 0], [1, 1]]}})
        self.assertEqual(set(TEMPLATES.keys()), before_keys)


# *********************************************************************
# Section 2 — Widget tests  (require PySide6)
# *********************************************************************

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    _HAS_PYSIDE = False
else:
    _HAS_PYSIDE = True


def _qapp() -> QtWidgets.QApplication:
    """Return a singleton QApplication (for offscreen test runs)."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app  # type: ignore[return-value]


@unittest.skipUnless(_HAS_PYSIDE, "PySide6 not installed")
class CurveCanvasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _qapp()

    def setUp(self) -> None:
        from app.ui.widgets.curve_canvas import CurveCanvas

        self.canvas = CurveCanvas()
        self.canvas.resize(240, 180)
        self.signal_count = 0

        def count() -> None:
            self.signal_count += 1

        self.canvas.changed.connect(count)  # type: ignore[attr-defined]

    def test_set_points_clamps_sorts_and_keeps_endpoints(self) -> None:
        self.canvas.set_points([(1.4, 2.0), (0.5, 0.25), (-1.0, -2.0)])

        self.assertEqual(self.canvas.points(), [(0.0, 0.0), (0.5, 0.25), (1.0, 1.0)])
        self.assertEqual(self.signal_count, 0)

    def test_add_point_selects_inserted_point_and_emits(self) -> None:
        index = self.canvas.add_point((0.5, 0.75))

        self.assertEqual(index, 1)
        self.assertEqual(self.canvas.selected_index(), 1)
        self.assertEqual(self.canvas.points(), [(0.0, 0.0), (0.5, 0.75), (1.0, 1.0)])
        self.assertEqual(self.signal_count, 1)

    def test_remove_selected_point_keeps_endpoints(self) -> None:
        self.canvas.add_point((0.5, 0.75))
        self.signal_count = 0

        removed = self.canvas.remove_selected_point()

        self.assertTrue(removed)
        self.assertEqual(self.canvas.points(), [(0.0, 0.0), (1.0, 1.0)])
        self.assertEqual(self.signal_count, 1)

    def test_remove_endpoint_is_noop(self) -> None:
        self.canvas.set_points([(0.0, 0.0), (1.0, 1.0)])
        self.canvas.add_point((0.0, 0.5))
        self.signal_count = 0

        removed = self.canvas.remove_selected_point()

        self.assertFalse(removed)
        self.assertEqual(self.signal_count, 0)

    def test_coordinate_roundtrip_uses_normalized_space(self) -> None:
        point = (0.25, 0.75)

        result = self.canvas.pos_to_point(self.canvas.point_to_pos(point))

        self.assertAlmostEqual(result[0], point[0])
        self.assertAlmostEqual(result[1], point[1])


@unittest.skipUnless(_HAS_PYSIDE, "PySide6 not installed")
class AimCurveEditorPureApiTests(unittest.TestCase):
    """Tests the non-visual API of AimCurveEditor.

    These tests construct the widget programmatically without showing it.
    """

    @classmethod
    def setUpClass(cls) -> None:
        _qapp()

    def setUp(self) -> None:
        from app.ui.widgets.curve_editor import AimCurveEditor

        self.editor = AimCurveEditor()
        self.signal_count = 0

        def count() -> None:
            self.signal_count += 1

        self.editor.changed.connect(count)  # type: ignore[attr-defined]
        # reset count from construction signals
        self.signal_count = 0

    def test_initial_state_empty(self) -> None:
        self.assertEqual(self.editor.curve_count(), 0)

    def test_load_curves_populates(self) -> None:
        from app.ui.widgets.curve_editor import TEMPLATES

        self.editor.load_curves(load_curves(TEMPLATES))  # type: ignore[arg-type]
        self.assertEqual(self.editor.curve_count(), 3)
        self.assertGreater(self.signal_count, 0)

    def test_load_extract_roundtrip(self) -> None:
        from app.ui.widgets.curve_editor import TEMPLATES

        self.editor.load_curves(load_curves(TEMPLATES))  # type: ignore[arg-type]
        exported = self.editor.extract_curves()
        self.assertEqual(set(exported.keys()), set(TEMPLATES.keys()))

    def test_add_curve_returns_id_and_selects(self) -> None:
        self.editor.load_curves(load_curves({"lin": {"label": "Linear", "points": [[0, 0], [1, 1]]}}))
        self.signal_count = 0
        cid = self.editor.add_curve("New Curve", [(0.0, 0.0), (1.0, 1.0)])
        self.assertEqual(cid, "new_curve")
        self.assertEqual(self.editor.curve_count(), 5)
        self.assertGreater(self.signal_count, 0)

    def test_add_curve_dup_name_gets_suffixed_id(self) -> None:
        self.editor.load_curves(load_curves({"linear": {"label": "Linear", "points": [[0, 0], [1, 1]]}}))
        cid = self.editor.add_curve("Linear", [(0.0, 0.0), (1.0, 1.0)])
        self.assertNotEqual(cid, "linear")  # should be linear_2 or similar

    def test_copy_current_curve(self) -> None:
        self.editor.load_curves(load_curves({"ex": {"label": "Expo", "points": [[0, 0], [1, 1]]}}))
        self.signal_count = 0
        new_id = self.editor.copy_current_curve("Expo Copy")
        self.assertIn("expo_copy", new_id)
        self.assertEqual(self.editor.curve_count(), 5)

    def test_remove_current_curve(self) -> None:
        self.editor.load_curves(load_curves({
            "a": {"label": "A", "points": [[0, 0], [1, 1]]},
            "b": {"label": "B", "points": [[0, 0.5], [1, 0.5]]},
        }))
        self.signal_count = 0
        self.editor.remove_current_curve()
        self.assertEqual(self.editor.curve_count(), 4)
        self.assertGreater(self.signal_count, 0)

    def test_builtin_curves_are_not_removed(self) -> None:
        from app.ui.widgets.curve_editor import TEMPLATES

        self.editor.load_curves(load_curves(TEMPLATES))  # type: ignore[arg-type]
        self.signal_count = 0

        self.editor.remove_current_curve()

        self.assertEqual(self.editor.curve_count(), len(TEMPLATES))
        self.assertEqual(self.signal_count, 0)

    def test_removing_only_custom_curve_leaves_builtins(self) -> None:
        self.editor.load_curves(load_curves({"a": {"label": "A", "points": [[0, 0], [1, 1]]}}))
        self.signal_count = 0
        self.editor.remove_current_curve()
        self.assertEqual(self.editor.curve_count(), 3)
        self.assertEqual(self.signal_count, 1)

    def test_rename_current_curve(self) -> None:
        self.editor.load_curves(load_curves({"lin": {"label": "Linear", "points": [[0, 0], [1, 1]]}}))
        self.signal_count = 0
        self.editor.rename_current_curve("Linear Renamed")
        exported = self.editor.extract_curves()
        self.assertNotIn("lin", exported)
        self.assertIn("linear_renamed", exported)
        self.assertEqual(exported["linear_renamed"]["label"], "Linear Renamed")
        self.assertGreater(self.signal_count, 0)

    def test_rename_updates_id(self) -> None:
        self.editor.load_curves(load_curves({"lin": {"label": "Linear", "points": [[0, 0], [1, 1]]}}))
        self.editor.rename_current_curve("New Name")
        self.assertNotIn("lin", self.editor.extract_curves())
        self.assertIn("new_name", self.editor.extract_curves())

    def test_name_field_renames_curve(self) -> None:
        self.editor.load_curves(load_curves({"lin": {"label": "Linear", "points": [[0, 0], [1, 1]]}}))
        self.signal_count = 0

        self.editor.name_edit.setText("Edited Name")
        self.editor.name_edit.editingFinished.emit()

        self.assertIn("edited_name", self.editor.extract_curves())
        self.assertEqual(self.signal_count, 1)

    def test_builtin_curves_are_read_only(self) -> None:
        from app.ui.widgets.curve_editor import TEMPLATES

        self.editor.load_curves(load_curves(TEMPLATES))  # type: ignore[arg-type]
        curve_id = self.editor.current_curve_id()
        before = self.editor.current_curve_points()
        self.signal_count = 0

        self.editor.rename_current_curve("Edited")
        self.editor.set_current_points([(0.0, 1.0), (1.0, 0.0)])
        self.editor.canvas.add_point((0.5, 0.5))

        self.assertEqual(self.editor.current_curve_id(), curve_id)
        self.assertEqual(self.editor.current_curve_points(), before)
        self.assertTrue(self.editor.name_edit.isReadOnly())
        self.assertFalse(self.editor.canvas.editable())
        self.assertEqual(self.signal_count, 0)

    def test_selecting_curve_does_not_emit_data_change(self) -> None:
        self.editor.load_curves(load_curves({
            "a": {"label": "A", "points": [[0, 0], [1, 1]]},
            "b": {"label": "B", "points": [[0, 0.5], [1, 0.5]]},
        }))
        self.signal_count = 0

        self.editor.curve_combo.setCurrentIndex(1)

        self.assertEqual(self.editor.current_curve_id(), "b")
        self.assertEqual(self.signal_count, 0)

    def test_set_current_points(self) -> None:
        self.editor.load_curves(load_curves({"lin": {"label": "Linear", "points": [[0, 0], [1, 1]]}}))
        self.signal_count = 0
        self.editor.set_current_points([(0.0, 0.0), (0.3, 0.7), (1.0, 1.0)])
        pts = self.editor.current_curve_points()
        self.assertEqual(len(pts), 3)
        self.assertAlmostEqual(pts[1][1], 0.7)
        self.assertEqual(self.editor.canvas.points(), pts)
        self.assertGreater(self.signal_count, 0)

    def test_set_current_points_clamps(self) -> None:
        self.editor.load_curves(load_curves({"lin": {"label": "Linear", "points": [[0, 0], [1, 1]]}}))
        self.editor.set_current_points([(0.0, 0.0), (1.5, 2.0)])
        pts = self.editor.current_curve_points()
        self.assertAlmostEqual(pts[-1][0], 1.0)
        self.assertAlmostEqual(pts[-1][1], 1.0)

    def test_current_curve_points_on_no_selection(self) -> None:
        self.assertEqual(self.editor.current_curve_points(), [])

    def test_template_points(self) -> None:
        pts = self.editor.template_points("linear")
        self.assertGreater(len(pts), 2)
        self.assertEqual(pts[0], [0.0, 0.0])
        self.assertEqual(pts[-1], [1.0, 1.0])

    def test_template_points_unknown(self) -> None:
        pts = self.editor.template_points("nonexistent")
        self.assertEqual(pts, [])

    def test_changed_signal_emitted_on_add(self) -> None:
        self.editor.load_curves(load_curves({"a": {"label": "A", "points": [[0, 0], [1, 1]]}}))
        self.signal_count = 0
        self.editor.add_curve("B", [(0.0, 0.0), (1.0, 1.0)])
        self.assertEqual(self.signal_count, 1)

    def test_changed_signal_emitted_on_copy(self) -> None:
        self.editor.load_curves(load_curves({"a": {"label": "A", "points": [[0, 0], [1, 1]]}}))
        self.signal_count = 0
        self.editor.copy_current_curve("Copy")
        self.assertEqual(self.signal_count, 1)

    def test_changed_signal_emitted_on_remove(self) -> None:
        self.editor.load_curves(load_curves({
            "a": {"label": "A", "points": [[0, 0], [1, 1]]},
            "b": {"label": "B", "points": [[0, 0.5], [1, 0.5]]},
        }))
        self.signal_count = 0
        self.editor.remove_current_curve()
        self.assertEqual(self.signal_count, 1)

    def test_changed_signal_emitted_on_rename(self) -> None:
        self.editor.load_curves(load_curves({"a": {"label": "A", "points": [[0, 0], [1, 1]]}}))
        self.signal_count = 0
        self.editor.rename_current_curve("Renamed")
        self.assertEqual(self.signal_count, 1)

    def test_changed_signal_emitted_on_set_points(self) -> None:
        self.editor.load_curves(load_curves({"a": {"label": "A", "points": [[0, 0], [1, 1]]}}))
        self.signal_count = 0
        self.editor.set_current_points([(0.0, 0.0), (1.0, 1.0)])
        self.assertEqual(self.signal_count, 1)

    def test_canvas_change_updates_current_curve(self) -> None:
        self.editor.load_curves(load_curves({"a": {"label": "A", "points": [[0, 0], [1, 1]]}}))
        self.signal_count = 0

        self.editor.canvas.add_point((0.4, 0.8))

        self.assertEqual(self.editor.current_curve_points(), [(0.0, 0.0), (0.4, 0.8), (1.0, 1.0)])
        self.assertEqual(self.signal_count, 1)

    def test_canvas_change_is_exported(self) -> None:
        self.editor.load_curves(load_curves({"a": {"label": "A", "points": [[0, 0], [1, 1]]}}))

        self.editor.canvas.add_point((0.4, 0.8))

        exported = self.editor.extract_curves()
        self.assertEqual(exported["a"]["points"], [[0.0, 0.0], [0.4, 0.8], [1.0, 1.0]])

    def test_changed_signal_not_emitted_on_remove_builtin(self) -> None:
        from app.ui.widgets.curve_editor import TEMPLATES

        self.editor.load_curves(load_curves(TEMPLATES))  # type: ignore[arg-type]
        self.signal_count = 0
        self.editor.remove_current_curve()
        self.assertEqual(self.signal_count, 0)  # noop → no signal


# *********************************************************************
# Section 3 — Adversarial / edge-case tests (pure helpers)
# *********************************************************************


class AdversarialTests(unittest.TestCase):
    """Malformed input, stale state, misleading-success patterns."""

    def test_clamp_sort_preserves_stability_on_equal_x(self) -> None:
        """Points with equal x values should both be kept (sort preserves both)."""
        result = clamp_sort_points([(0.5, 0.3), (0.5, 0.7)])
        self.assertEqual(len(result), 2)

    def test_normalize_curve_very_large_values_clamped(self) -> None:
        raw = {"label": "big", "points": [[-1e6, -1e6], [1e6, 1e6]]}
        result = normalize_curve(raw)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertAlmostEqual(result["points"][0][0], 0.0)
        self.assertAlmostEqual(result["points"][0][1], 0.0)
        self.assertAlmostEqual(result["points"][-1][0], 1.0)
        self.assertAlmostEqual(result["points"][-1][1], 1.0)

    def test_load_curves_with_all_keys_blank(self) -> None:
        """Whitespace-only keys should be rejected."""
        result = load_curves({"": {"label": "X", "points": [[0, 0], [1, 1]]}})
        # falls back to templates since no valid key
        self.assertGreaterEqual(len(result), 3)

    def test_unique_id_handles_unicode(self) -> None:
        self.assertIn(unique_id("\u00c9lan", set()), {"lan", "lan_2", "lan_3"})

    def test_extract_curves_strips_internal_keys(self) -> None:
        internal = load_curves({"x": {"label": "X", "points": [[0, 0], [1, 1]]}})
        exported = extract_curves(internal)
        self.assertNotIn("_id", exported["x"])
        # No other dunder keys leaked
        for k in exported["x"]:
            self.assertFalse(k.startswith("_"))

    def test_id_from_label_preserves_numbers(self) -> None:
        self.assertEqual(id_from_label("50% Power"), "50_power")

    def test_curve_editor_imports_when_pyside_is_missing(self) -> None:
        script = textwrap.dedent(
            """
            import builtins

            real_import = builtins.__import__

            def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name == 'PySide6' or name.startswith('PySide6.'):
                    raise ImportError(name)
                return real_import(name, globals, locals, fromlist, level)

            builtins.__import__ = guarded_import
            from app.ui.widgets.curve_editor import AimCurveEditor
            editor = AimCurveEditor()
            assert editor.extract_curves() == {}
            """
        )

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[1],
            env={"PYTHONPATH": "."},
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
