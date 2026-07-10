from __future__ import annotations

import os
import sys
import unittest
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from app.ui.widgets.cv_trigger_editor import CVTriggerEditor, _normalize_cv_trigger_config_for_ui  # noqa: E402


def _make_editor() -> CVTriggerEditor:
    return CVTriggerEditor("cv_trigger", "CV Trigger", device_service=None)


def _base_config() -> dict[str, Any]:
    return {
        "enabled": True,
        "model_path": "/models/best.pt",
        "monitor": {"top": 0, "left": 0, "width": 2560, "height": 1440},
        "game_resolution": {"width": 1600, "height": 1200},
        "inference_confidence": 0.15,
        "inference_img_size": 384,
        "configs": {
            "pistol_alt": {
                "enabled": True,
                "activation": {"device": "keyboard", "key": "alt"},
                "auto_shoot": True,
                "target_type": "both",
            },
        },
    }


class RoundTripTests(unittest.TestCase):
    def test_multiple_curves_round_trip(self) -> None:
        curves = {
            "custom_a": {
                "label": "Custom A",
                "points": [[0.0, 0.0], [0.5, 0.3], [1.0, 1.0]],
            },
            "custom_b": {
                "label": "Custom B",
                "points": [[0.0, 0.1], [1.0, 0.9]],
            },
        }
        config = _base_config()
        config["aim_curves"] = curves

        editor = _make_editor()
        editor.load_config(config)

        extracted = editor.extract_config()
        self.assertIn("aim_curves", extracted)
        out = extracted["aim_curves"]
        self.assertIn("custom_a", out)
        self.assertIn("custom_b", out)
        self.assertEqual(out["custom_a"]["label"], "Custom A")
        self.assertEqual(len(out["custom_a"]["points"]), 3)
        self.assertEqual(out["custom_b"]["label"], "Custom B")
        self.assertEqual(len(out["custom_b"]["points"]), 2)

    def test_extracted_points_are_serializable(self) -> None:
        config = _base_config()
        config["aim_curves"] = {
            "lin": {"label": "Linear", "points": [[0.0, 0.0], [1.0, 1.0]]},
        }
        editor = _make_editor()
        editor.load_config(config)

        extracted = editor.extract_config()
        pts = extracted["aim_curves"]["lin"]["points"]
        for pt in pts:
            self.assertIsInstance(pt, list)
            self.assertEqual(len(pt), 2)
            self.assertIsInstance(pt[0], float)
            self.assertIsInstance(pt[1], float)


class NormalizeTests(unittest.TestCase):
    def test_missing_aim_curves_normalizes_to_templates(self) -> None:
        cfg = _normalize_cv_trigger_config_for_ui({"configs": {}})
        self.assertIn("aim_curves", cfg)
        self.assertIn("linear", cfg["aim_curves"])
        self.assertIn("exponential", cfg["aim_curves"])
        self.assertIn("constant_50", cfg["aim_curves"])

    def test_malformed_aim_curves_drops_invalid(self) -> None:
        cfg = _normalize_cv_trigger_config_for_ui({
            "aim_curves": {
                "good": {"label": "Good", "points": [[0, 0], [1, 1]]},
                "bad": "not a curve",
                "no_points": {"label": "NP"},
                "too_few": {"label": "TF", "points": [[0, 0]]},
            },
            "configs": {},
        })
        self.assertIn("good", cfg["aim_curves"])
        self.assertNotIn("bad", cfg["aim_curves"])
        self.assertNotIn("no_points", cfg["aim_curves"])
        self.assertNotIn("too_few", cfg["aim_curves"])

    def test_none_aim_curves_normalizes_to_templates(self) -> None:
        cfg = _normalize_cv_trigger_config_for_ui({
            "aim_curves": None,
            "configs": {},
        })
        self.assertIn("aim_curves", cfg)
        self.assertIn("linear", cfg["aim_curves"])

    def test_empty_dict_aim_curves_normalizes_to_templates(self) -> None:
        cfg = _normalize_cv_trigger_config_for_ui({
            "aim_curves": {},
            "configs": {},
        })
        self.assertIn("aim_curves", cfg)
        self.assertIn("linear", cfg["aim_curves"])


class SignalTests(unittest.TestCase):
    def test_curve_editor_mutation_emits_config_changed(self) -> None:
        editor = _make_editor()
        editor.load_config(_base_config())

        received: list[tuple[str, dict[str, Any]]] = []
        editor.config_changed.connect(lambda name, cfg: received.append((name, cfg)))
        editor.aim_curve_editor.add_curve("Test Curve", [(0.0, 0.0), (1.0, 1.0)])
        self.assertTrue(len(received) > 0, "config_changed not emitted after curve add")
        self.assertEqual(received[0][0], "cv_trigger")


class PreservesExistingTests(unittest.TestCase):
    def test_existing_rules_preserved(self) -> None:
        config = _base_config()
        config["configs"]["rifle"] = {
            "enabled": False,
            "activation": {"mode": "always"},
            "auto_shoot": False,
            "target_type": "head",
        }
        config["aim_curves"] = {
            "my_curve": {"label": "MC", "points": [[0, 0], [1, 1]]},
        }

        editor = _make_editor()
        editor.load_config(config)

        extracted = editor.extract_config()
        self.assertEqual(len(extracted["configs"]), 2)
        self.assertIn("pistol_alt", extracted["configs"])
        self.assertIn("rifle", extracted["configs"])

    def test_other_top_level_fields_preserved(self) -> None:
        config = _base_config()
        config["use_gsi_opponent_side"] = True
        config["manual_target_side"] = "terrorists"

        editor = _make_editor()
        editor.load_config(config)

        extracted = editor.extract_config()
        self.assertTrue(extracted["use_gsi_opponent_side"])
        self.assertEqual(extracted["manual_target_side"], "terrorists")

    def test_model_path_round_trips(self) -> None:
        config = _base_config()
        config["model_path"] = "/custom/model.pt"

        editor = _make_editor()
        editor.load_config(config)

        extracted = editor.extract_config()
        self.assertEqual(extracted["model_path"], "/custom/model.pt")


if __name__ == "__main__":
    unittest.main()
