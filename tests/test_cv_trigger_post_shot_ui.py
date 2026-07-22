from __future__ import annotations

import os
import sys
import types
import unittest
from typing import Any

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if "mss" not in sys.modules:
    mss_stub = types.ModuleType("mss")
    mss_stub.mss = object
    sys.modules["mss"] = mss_stub

try:
    from PySide6 import QtWidgets
except ImportError as exc:
    QtWidgets = None
    QT_IMPORT_ERROR = exc
else:
    QT_IMPORT_ERROR = None

if QtWidgets is not None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    from app.device_service import DeviceService
    from app.ui.widgets.cv_trigger_editor import CVTriggerEditor, _normalize_cv_trigger_config_for_ui


def _make_editor() -> CVTriggerEditor:
    assert QtWidgets is not None
    return CVTriggerEditor("cv_trigger", "CV Trigger", device_service=DeviceService())


def _base_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "model_path": "/models/best.pt",
        "configs": {
            "pistol_alt": {
                "enabled": True,
                "activation": {"device": "keyboard", "key": "alt"},
                "auto_shoot": True,
                "target_type": "both",
            },
        },
    }


@unittest.skipIf(QT_IMPORT_ERROR is not None, f"PySide6 is unavailable: {QT_IMPORT_ERROR}")
class PostShotYConfigUiTests(unittest.TestCase):
    def test_missing_config_normalizes_to_disabled_defaults(self) -> None:
        normalized = _normalize_cv_trigger_config_for_ui({"configs": {}})

        post_shot = normalized["post_shot_y_suppression"]
        self.assertFalse(post_shot["enabled"])
        self.assertEqual(post_shot["stabilization_strength"], 1.0)
        self.assertEqual(post_shot["horizontal_stabilization_strength"], 0.5)
        self.assertEqual(post_shot["manual_release_max_hold_ms"], 300)
        self.assertNotIn("fire_interval_hold_fraction", post_shot)
        self.assertNotIn("recoil_hold_ms_per_amount", post_shot)

    def test_legacy_internal_config_normalizes_to_simple_controls(self) -> None:
        normalized = _normalize_cv_trigger_config_for_ui({
            "configs": {},
            "post_shot_y_suppression": {
                "enabled": True,
                "min_downward_scale": 0.25,
                "fallback_hold_ms": 80,
                "fallback_restore_ms": 120,
            },
        })

        post_shot = normalized["post_shot_y_suppression"]
        self.assertTrue(post_shot["enabled"])
        self.assertAlmostEqual(post_shot["stabilization_strength"], 0.75 / 0.98)
        self.assertEqual(post_shot["horizontal_stabilization_strength"], 0.5)
        self.assertEqual(post_shot["manual_release_max_hold_ms"], 300)
        self.assertEqual(
            set(post_shot),
            {"enabled", "stabilization_strength", "horizontal_stabilization_strength", "manual_release_max_hold_ms"},
        )

    def test_editor_loads_and_extracts_post_shot_y_settings(self) -> None:
        config = _base_config()
        config["post_shot_y_suppression"] = {
            "enabled": True,
            "stabilization_strength": 1.25,
            "horizontal_stabilization_strength": 0.40,
            "manual_release_max_hold_ms": 425,
        }
        editor = _make_editor()

        editor.load_config(config)
        extracted = editor.extract_config()["post_shot_y_suppression"]

        self.assertTrue(extracted["enabled"])
        self.assertEqual(extracted["stabilization_strength"], 1.25)
        self.assertEqual(extracted["horizontal_stabilization_strength"], 0.40)
        self.assertEqual(extracted["manual_release_max_hold_ms"], 425)
        self.assertEqual(
            set(extracted),
            {"enabled", "stabilization_strength", "horizontal_stabilization_strength", "manual_release_max_hold_ms"},
        )

    def test_editor_controls_can_calibrate_values(self) -> None:
        editor = _make_editor()
        editor.load_config(_base_config())

        editor.post_shot_y_enabled.setChecked(True)
        editor.post_shot_y_stabilization_strength.setValue(125.0)
        editor.post_shot_x_stabilization_strength.setValue(40.0)
        editor.post_shot_manual_release_max_hold_ms.setValue(450)

        extracted = editor.extract_config()["post_shot_y_suppression"]
        self.assertTrue(extracted["enabled"])
        self.assertEqual(extracted["stabilization_strength"], 1.25)
        self.assertEqual(extracted["horizontal_stabilization_strength"], 0.40)
        self.assertEqual(extracted["manual_release_max_hold_ms"], 450)

    def test_editor_allows_strength_above_old_150_percent_ceiling(self) -> None:
        editor = _make_editor()
        editor.load_config(_base_config())

        editor.post_shot_y_enabled.setChecked(True)
        editor.post_shot_y_stabilization_strength.setValue(400.0)
        editor.post_shot_x_stabilization_strength.setValue(250.0)

        extracted = editor.extract_config()["post_shot_y_suppression"]
        self.assertTrue(extracted["enabled"])
        self.assertEqual(extracted["stabilization_strength"], 4.0)
        self.assertEqual(extracted["horizontal_stabilization_strength"], 2.5)


if __name__ == "__main__":
    _ = unittest.main()
