from __future__ import annotations

import os
import sys
import unittest
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from app.ui.widgets.cv_rule_editor import CVRuleEditor  # noqa: E402
from app.ui.widgets.cv_trigger_editor import CVTriggerEditor  # noqa: E402


LEGACY_KEYS = {
    "RESPONSE_CURVE",
    "CURVE_INTENSITY",
    "CONSTANT_SPEED_PX",
    "ACCEL_BOOST",
    "ANTI_OVERSHOOT",
}


def _rule_editor() -> CVRuleEditor:
    editor = CVRuleEditor()
    editor.set_available_curves({
        "linear": {"label": "Linear", "points": [[0.0, 0.0], [1.0, 1.0]]},
        "custom": {"label": "Custom Curve", "points": [[0.0, 0.2], [1.0, 0.8]]},
    })
    return editor


def _canonical_rule() -> dict[str, Any]:
    return {
        "enabled": True,
        "activation": {"mode": "always"},
        "auto_shoot": True,
        "target_type": "both",
        "AIM_MODE": "head",
        "HEAD_OFFSET": 0.12,
        "BODY_KNEE_OFFSET": 0.5,
        "AIM_STRENGTH": 1.25,
        "AIM_CURVE_ID": "custom",
        "MAX_AIM_SPEED_PX": 70,
        "SNAP_DISTANCE": 250,
        "SMOOTHING_ALPHA": 0.2,
        "NOISE_AMOUNT": 2.5,
        "CROSS_X_THRESH": 14,
        "CROSS_Y_THRESH_TOP": 18,
        "CROSS_Y_THRESH_BOT": 32,
    }


class CVRuleEditorCanonicalTests(unittest.TestCase):
    def test_extract_rule_outputs_canonical_aim_keys(self) -> None:
        editor = _rule_editor()
        editor.load_rule("rifle", _canonical_rule())

        name, rule = editor.extract_rule()

        self.assertEqual(name, "rifle")
        self.assertEqual(rule["AIM_CURVE_ID"], "custom")
        self.assertEqual(rule["AIM_STRENGTH"], 1.25)
        self.assertEqual(rule["MAX_AIM_SPEED_PX"], 70)
        self.assertEqual(rule["SNAP_DISTANCE"], 250)
        self.assertEqual(rule["NOISE_AMOUNT"], 2.5)
        self.assertTrue(LEGACY_KEYS.isdisjoint(rule))

    def test_aim_strength_is_scalar_without_percent_suffix(self) -> None:
        editor = _rule_editor()
        editor.load_rule("rifle", _canonical_rule() | {"AIM_STRENGTH": 12.5})

        self.assertEqual(editor.aim_strength.suffix(), "")
        self.assertGreaterEqual(editor.aim_strength.maximum(), 20.0)
        self.assertEqual(editor.extract_rule()[1]["AIM_STRENGTH"], 12.5)

    def test_legacy_rule_input_is_tolerated_but_not_extracted(self) -> None:
        editor = _rule_editor()
        editor.load_rule(
            "legacy",
            {
                "AIM_STRENGTH": 75.0,
                "RESPONSE_CURVE": "proportional",
                "CONSTANT_SPEED_PX": 55,
                "CURVE_INTENSITY": 1.5,
                "ACCEL_BOOST": 2.0,
                "ANTI_OVERSHOOT": True,
            },
        )

        rule = editor.extract_rule()[1]

        self.assertEqual(rule["AIM_STRENGTH"], 0.75)
        self.assertEqual(rule["AIM_CURVE_ID"], "linear")
        self.assertEqual(rule["MAX_AIM_SPEED_PX"], 55)
        self.assertTrue(LEGACY_KEYS.isdisjoint(rule))

    def test_missing_curve_selection_falls_back_to_available_curve(self) -> None:
        editor = _rule_editor()
        editor.load_rule("missing", _canonical_rule() | {"AIM_CURVE_ID": "removed"})

        self.assertEqual(editor.extract_rule()[1]["AIM_CURVE_ID"], "linear")


class CVTriggerEditorCurveIntegrationTests(unittest.TestCase):
    def test_rule_editors_receive_global_curve_library(self) -> None:
        editor = CVTriggerEditor("cv_trigger", "CV Trigger", device_service=None)
        editor.load_config({
            "enabled": True,
            "aim_curves": {
                "custom": {"label": "Custom", "points": [[0.0, 0.0], [1.0, 1.0]]},
            },
            "configs": {"rule": _canonical_rule() | {"AIM_CURVE_ID": "custom"}},
        })

        extracted = editor.extract_config()

        self.assertEqual(extracted["configs"]["rule"]["AIM_CURVE_ID"], "custom")
        self.assertTrue(LEGACY_KEYS.isdisjoint(extracted["configs"]["rule"]))


if __name__ == "__main__":
    unittest.main()
