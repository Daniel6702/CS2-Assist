from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from app.components.cv_trigger.migration import (
    _PRESET_CURVES,
    _build_curve_library,
    _LEGACY_CURVE_MAP,
    _migrate_legacy_config,
    _migrate_rule,
    _to_scalar_aim_strength,
)
from app.defaults import default_profile


class ToScalarAimStrengthTests(unittest.TestCase):
    def test_percent_values_divide_by_100(self) -> None:
        self.assertEqual(_to_scalar_aim_strength(50.0), 0.5)
        self.assertEqual(_to_scalar_aim_strength(100.0), 1.0)
        self.assertEqual(_to_scalar_aim_strength(20.0), 0.2)
        self.assertEqual(_to_scalar_aim_strength(90.0), 0.9)

    def test_already_scalar_values_preserved(self) -> None:
        self.assertEqual(_to_scalar_aim_strength(0.5), 0.5)
        self.assertEqual(_to_scalar_aim_strength(1.0), 1.0)
        self.assertEqual(_to_scalar_aim_strength(0.0), 0.0)
        self.assertEqual(_to_scalar_aim_strength(0.75), 0.75)

    def test_edge_values(self) -> None:
        self.assertAlmostEqual(_to_scalar_aim_strength(1.1, legacy_percent=False), 1.1)
        self.assertAlmostEqual(_to_scalar_aim_strength(2.0, legacy_percent=False), 2.0)
        self.assertAlmostEqual(_to_scalar_aim_strength(101.0), 1.01)
        self.assertAlmostEqual(_to_scalar_aim_strength(0.01), 0.01)  # already scalar


class BuildCurveLibraryTests(unittest.TestCase):
    def test_returns_deep_copy(self) -> None:
        lib = _build_curve_library()
        lib["linear"]["label"] = "CHANGED"
        lib["linear"]["points"][0][1] = 0.5
        original = _build_curve_library()
        self.assertEqual(original["linear"]["label"], "Linear")
        self.assertEqual(original["linear"]["points"][0][1], 0.0)
        self.assertEqual(lib["linear"]["label"], "CHANGED")

    def test_contains_all_presets(self) -> None:
        lib = _build_curve_library()
        self.assertIn("constant_50", lib)
        self.assertIn("linear", lib)
        self.assertIn("exponential", lib)
        self.assertEqual(len(lib), 3)

    def test_each_curve_has_label_and_points(self) -> None:
        lib = _build_curve_library()
        for cid, curve in lib.items():
            self.assertIn("label", curve, f"curve {cid} missing label")
            self.assertIn("points", curve, f"curve {cid} missing points")
            self.assertIsInstance(curve["points"], list)
            self.assertGreater(len(curve["points"]), 0)

    def test_normalized_points(self) -> None:
        lib = _build_curve_library()
        for cid, curve in lib.items():
            for pt in curve["points"]:
                x, y = pt
                self.assertGreaterEqual(x, 0.0, f"{cid} x < 0")
                self.assertLessEqual(x, 1.0, f"{cid} x > 1")
                self.assertGreaterEqual(y, 0.0, f"{cid} y < 0")
                self.assertLessEqual(y, 1.0, f"{cid} y > 1")


class LegacyCurveMapTests(unittest.TestCase):
    def test_maps_known_types(self) -> None:
        self.assertEqual(_LEGACY_CURVE_MAP["proportional"], "linear")
        self.assertEqual(_LEGACY_CURVE_MAP["accelerating"], "exponential")
        self.assertEqual(_LEGACY_CURVE_MAP["constant"], "constant_50")

    def test_unknown_type_defaults_to_linear_in_caller(self) -> None:
        # _LEGACY_CURVE_MAP itself returns None for unknown,
        # but _migrate_rule maps that to "linear"
        self.assertNotIn("unknown", _LEGACY_CURVE_MAP)


class MigrateRuleTests(unittest.TestCase):
    def test_converts_percent_aim_strength_to_scalar(self) -> None:
        result = _migrate_rule({"AIM_STRENGTH": 50.0})
        self.assertEqual(result["AIM_STRENGTH"], 0.5)

    def test_preserves_already_scalar_aim_strength(self) -> None:
        result = _migrate_rule({"AIM_STRENGTH": 0.5})
        self.assertEqual(result["AIM_STRENGTH"], 0.5)

    def test_preserves_canonical_scalar_above_one(self) -> None:
        result = _migrate_rule({
            "AIM_STRENGTH": 2.0,
            "AIM_CURVE_ID": "linear",
            "MAX_AIM_SPEED_PX": 50,
        })
        self.assertEqual(result["AIM_STRENGTH"], 2.0)

    def test_legacy_shape_converts_percent_above_one(self) -> None:
        result = _migrate_rule({"AIM_STRENGTH": 75.0, "RESPONSE_CURVE": "proportional"})
        self.assertEqual(result["AIM_STRENGTH"], 0.75)

    def test_zero_aim_strength_stays_zero(self) -> None:
        result = _migrate_rule({"AIM_STRENGTH": 0.0})
        self.assertEqual(result["AIM_STRENGTH"], 0.0)

    def test_sets_default_aim_strength_when_missing(self) -> None:
        result = _migrate_rule({})
        self.assertEqual(result["AIM_STRENGTH"], 0.5)

    def test_priority_defaults_to_zero_when_missing_or_invalid(self) -> None:
        self.assertEqual(_migrate_rule({})["priority"], 0)
        self.assertEqual(_migrate_rule({"priority": "bad"})["priority"], 0)

    def test_priority_is_preserved_as_integer(self) -> None:
        self.assertEqual(_migrate_rule({"priority": "2"})["priority"], 2)

    def test_maps_legacy_response_curve_to_aim_curve_id(self) -> None:
        result = _migrate_rule({"RESPONSE_CURVE": "proportional"})
        self.assertEqual(result["AIM_CURVE_ID"], "linear")
        self.assertNotIn("RESPONSE_CURVE", result)

        result = _migrate_rule({"RESPONSE_CURVE": "accelerating"})
        self.assertEqual(result["AIM_CURVE_ID"], "exponential")

        result = _migrate_rule({"RESPONSE_CURVE": "constant"})
        self.assertEqual(result["AIM_CURVE_ID"], "constant_50")

    def test_case_insensitive_curve_mapping(self) -> None:
        result = _migrate_rule({"RESPONSE_CURVE": "Proportional"})
        self.assertEqual(result["AIM_CURVE_ID"], "linear")
        result = _migrate_rule({"RESPONSE_CURVE": "ACCELERATING"})
        self.assertEqual(result["AIM_CURVE_ID"], "exponential")

    def test_unknown_curve_defaults_to_linear(self) -> None:
        result = _migrate_rule({"RESPONSE_CURVE": "unknown_curve"})
        self.assertEqual(result["AIM_CURVE_ID"], "linear")

    def test_preserves_existing_aim_curve_id_when_no_response_curve(self) -> None:
        result = _migrate_rule({"AIM_CURVE_ID": "exponential"})
        self.assertEqual(result["AIM_CURVE_ID"], "exponential")

    def test_removes_curve_intensity(self) -> None:
        result = _migrate_rule({"CURVE_INTENSITY": 1.5})
        self.assertNotIn("CURVE_INTENSITY", result)

    def test_converts_constant_speed_px_to_max_aim_speed_px(self) -> None:
        result = _migrate_rule({"CONSTANT_SPEED_PX": 75})
        self.assertEqual(result["MAX_AIM_SPEED_PX"], 75)
        self.assertNotIn("CONSTANT_SPEED_PX", result)

    def test_default_max_aim_speed_px(self) -> None:
        result = _migrate_rule({})
        self.assertEqual(result["MAX_AIM_SPEED_PX"], 50)

    def test_removes_accel_boost(self) -> None:
        result = _migrate_rule({"ACCEL_BOOST": 2.0})
        self.assertNotIn("ACCEL_BOOST", result)

    def test_removes_anti_overshoot(self) -> None:
        result = _migrate_rule({"ANTI_OVERSHOOT": True})
        self.assertNotIn("ANTI_OVERSHOOT", result)

    def test_preserves_snap_distance(self) -> None:
        result = _migrate_rule({"SNAP_DISTANCE": 300})
        self.assertEqual(result["SNAP_DISTANCE"], 300)

    def test_preserves_smoothing_alpha(self) -> None:
        result = _migrate_rule({"SMOOTHING_ALPHA": 0.8})
        self.assertEqual(result["SMOOTHING_ALPHA"], 0.8)

    def test_preserves_noise_amount(self) -> None:
        result = _migrate_rule({"NOISE_AMOUNT": 0.1})
        self.assertEqual(result["NOISE_AMOUNT"], 0.1)

    def test_preserves_non_curve_fields(self) -> None:
        result = _migrate_rule({
            "AIM_MODE": "head",
            "HEAD_OFFSET": 0.12,
            "COOLDOWN_MS": 250,
            "activation": {"device": "keyboard", "key": "alt"},
        })
        self.assertEqual(result["AIM_MODE"], "head")
        self.assertEqual(result["HEAD_OFFSET"], 0.12)
        self.assertEqual(result["COOLDOWN_MS"], 250)

    def test_sens_coeff_conversion_via_raw_item(self) -> None:
        raw = {"SENS_COEFF": 1.0}
        result = _migrate_rule({"AIM_STRENGTH": 50.0}, raw)
        # AIM_STRENGTH already present, SENS_COEFF ignored
        self.assertEqual(result["AIM_STRENGTH"], 0.5)
        self.assertNotIn("SENS_COEFF", result)

    def test_sens_coeff_fills_missing_aim_strength_via_raw_item(self) -> None:
        raw = {"SENS_COEFF": 2.0}
        result = _migrate_rule({"SNAP_DISTANCE": 200}, raw)
        # SENS_COEFF 2.0 * 50 = 100.0, then /100 = 1.0
        self.assertEqual(result["AIM_STRENGTH"], 1.0)
        self.assertNotIn("SENS_COEFF", result)

    def test_does_not_mutate_input_dict(self) -> None:
        inp = {"AIM_STRENGTH": 50.0, "RESPONSE_CURVE": "proportional"}
        _migrate_rule(inp)
        self.assertIn("AIM_STRENGTH", inp)
        self.assertIn("RESPONSE_CURVE", inp)  # original not mutated

    def test_removes_old_runtime_keys_entirely(self) -> None:
        result = _migrate_rule({
            "RESPONSE_CURVE": "proportional",
            "CURVE_INTENSITY": 1.0,
            "CONSTANT_SPEED_PX": 50,
            "ACCEL_BOOST": 1.0,
            "ANTI_OVERSHOOT": True,
        })
        for key in ("RESPONSE_CURVE", "CURVE_INTENSITY", "CONSTANT_SPEED_PX", "ACCEL_BOOST", "ANTI_OVERSHOOT"):
            self.assertNotIn(key, result, f"{key} still present in migrated rule")


class MigrateLegacyConfigTests(unittest.TestCase):
    def test_adds_curve_library_when_missing(self) -> None:
        config = {"configs": {"test_rule": {"AIM_STRENGTH": 50.0}}}
        result = _migrate_legacy_config(config)
        self.assertIn("aim_curves", result)
        self.assertIn("linear", result["aim_curves"])
        self.assertIn("exponential", result["aim_curves"])
        self.assertIn("constant_50", result["aim_curves"])

    def test_preserves_existing_curve_library(self) -> None:
        config = {
            "aim_curves": {"custom": {"label": "Custom", "points": [[0, 0], [1, 1]]}},
            "configs": {"test_rule": {"AIM_STRENGTH": 50.0}},
        }
        result = _migrate_legacy_config(config)
        self.assertIn("custom", result["aim_curves"])
        self.assertNotIn("constant_50", result["aim_curves"])

    def test_legacy_profile_branch_adds_curves(self) -> None:
        config = {
            "active_profile": "pistol",
            "hold_mode": "alt",
            "profiles": {
                "pistol": {
                    "AIM_STRENGTH": 60.0,
                    "RESPONSE_CURVE": "proportional",
                    "CONSTANT_SPEED_PX": 50,
                    "ACCEL_BOOST": 1.0,
                    "ANTI_OVERSHOOT": True,
                    "SMOOTHING_ALPHA": 0.0,
                    "NOISE_AMOUNT": 0.0,
                    "AUTO_SHOOT_ZONE_WIDTH": 28,
                    "AUTO_SHOOT_ZONE_HEIGHT": 36,
                    "AUTO_SHOOT_ZONE_Y_POS": 0.35,
                },
            },
        }
        result = _migrate_legacy_config(config)
        self.assertIn("aim_curves", result)

    def test_legacy_profile_branch_creates_single_config(self) -> None:
        config = {
            "active_profile": "pistol",
            "hold_mode": "alt",
            "profiles": {
                "pistol": {
                    "AIM_STRENGTH": 60.0,
                    "RESPONSE_CURVE": "proportional",
                    "CONSTANT_SPEED_PX": 50,
                },
            },
        }
        result = _migrate_legacy_config(config)
        self.assertIn("configs", result)
        self.assertIn("pistol", result["configs"])
        rule = result["configs"]["pistol"]
        self.assertEqual(rule["AIM_STRENGTH"], 0.6)
        self.assertEqual(rule["AIM_CURVE_ID"], "linear")

    def test_legacy_profile_branch_uses_defaults_when_empty(self) -> None:
        config = {"active_profile": "pistol", "hold_mode": "alt", "profiles": {}}
        result = _migrate_legacy_config(config)
        self.assertIn("pistol", result["configs"])
        rule = result["configs"]["pistol"]
        self.assertEqual(rule["AIM_STRENGTH"], 0.6)  # 60.0 from fallback default /100
        self.assertIn("AIM_CURVE_ID", rule)
        self.assertIn("MAX_AIM_SPEED_PX", rule)

    def test_multiple_configs_all_migrated(self) -> None:
        config = {
            "configs": {
                "a": {"AIM_STRENGTH": 50.0, "RESPONSE_CURVE": "proportional", "CONSTANT_SPEED_PX": 40},
                "b": {"AIM_STRENGTH": 80.0, "RESPONSE_CURVE": "accelerating", "CONSTANT_SPEED_PX": 60},
            },
        }
        result = _migrate_legacy_config(config)
        self.assertIn("a", result["configs"])
        self.assertIn("b", result["configs"])
        self.assertEqual(result["configs"]["a"]["AIM_STRENGTH"], 0.5)
        self.assertEqual(result["configs"]["a"]["AIM_CURVE_ID"], "linear")
        self.assertEqual(result["configs"]["b"]["AIM_STRENGTH"], 0.8)
        self.assertEqual(result["configs"]["b"]["AIM_CURVE_ID"], "exponential")

    def test_legacy_keys_not_in_output_configs(self) -> None:
        config = {
            "configs": {
                "test": {
                    "AIM_STRENGTH": 50.0,
                    "RESPONSE_CURVE": "proportional",
                    "CURVE_INTENSITY": 1.0,
                    "CONSTANT_SPEED_PX": 50,
                    "ACCEL_BOOST": 1.0,
                    "ANTI_OVERSHOOT": True,
                    "NOISE_AMOUNT": 0.0,
                    "SNAP_DISTANCE": 200,
                },
            },
        }
        result = _migrate_legacy_config(config)
        rule = result["configs"]["test"]
        for key in ("RESPONSE_CURVE", "CURVE_INTENSITY", "CONSTANT_SPEED_PX", "ACCEL_BOOST", "ANTI_OVERSHOOT"):
            self.assertNotIn(key, rule, f"{key} leaked into canonical output")

    def test_sens_coeff_in_configs_branch(self) -> None:
        config = {
            "configs": {
                "test": {"SENS_COEFF": 1.5, "CONSTANT_SPEED_PX": 50},
            },
        }
        result = _migrate_legacy_config(config)
        rule = result["configs"]["test"]
        # SENS_COEFF 1.5 * 50 = 75.0, /100 = 0.75
        self.assertEqual(rule["AIM_STRENGTH"], 0.75)
        self.assertNotIn("SENS_COEFF", rule)

    def test_preserves_non_curve_config_fields(self) -> None:
        config = {
            "configs": {
                "test": {
                    "AIM_STRENGTH": 50.0,
                    "enabled": True,
                    "auto_shoot": False,
                    "allowed_weapons": ["weapon_ak47"],
                    "activation": {"device": "keyboard", "key": "alt"},
                    "target_type": "both",
                },
            },
        }
        result = _migrate_legacy_config(config)
        rule = result["configs"]["test"]
        self.assertEqual(rule["enabled"], True)
        self.assertEqual(rule["auto_shoot"], False)
        self.assertEqual(rule["allowed_weapons"], ["weapon_ak47"])
        self.assertEqual(rule["target_type"], "both")

    def test_top_level_fields_preserved(self) -> None:
        config = {
            "enabled": True,
            "model_path": "/some/model.pt",
            "configs": {"test": {"AIM_STRENGTH": 50.0}},
        }
        result = _migrate_legacy_config(config)
        self.assertEqual(result["enabled"], True)
        self.assertEqual(result["model_path"], "/some/model.pt")

    def test_missing_configs_uses_legacy_profile_branch(self) -> None:
        config = {"CONFIDENCE": 0.3, "IMG_SIZE": 640, "active_profile": "rifle", "hold_mode": "alt"}
        result = _migrate_legacy_config(config)
        self.assertIn("configs", result)
        self.assertIn("inference_confidence", result)
        self.assertIn("inference_img_size", result)

    def test_non_dict_configs_uses_legacy_profile_branch(self) -> None:
        config = {"configs": None, "CONFIDENCE": 0.3, "IMG_SIZE": 640}
        result = _migrate_legacy_config(config)
        self.assertIn("configs", result)

    def test_stale_state_empty_configs(self) -> None:
        config = {"configs": {}}
        result = _migrate_legacy_config(config)
        self.assertEqual(result["configs"], {})
        self.assertIn("aim_curves", result)

    def test_stale_state_missing_raw_item(self) -> None:
        config = {"configs": {"test": None}}
        result = _migrate_legacy_config(config)
        rule = result["configs"]["test"]
        self.assertEqual(rule["AIM_STRENGTH"], 0.5)
        self.assertEqual(rule["MAX_AIM_SPEED_PX"], 50)

    def test_partial_aim_strength_weird_values(self) -> None:
        config = {
            "configs": {
                "a": {"AIM_STRENGTH": "wrong", "CONSTANT_SPEED_PX": 50},
                "b": {"CONSTANT_SPEED_PX": 30},
                "c": {"AIM_STRENGTH": None, "CONSTANT_SPEED_PX": 50},
            },
        }
        result = _migrate_legacy_config(config)
        self.assertEqual(result["configs"]["a"]["AIM_STRENGTH"], 0.5)  # default from setdefault
        self.assertEqual(result["configs"]["b"]["AIM_STRENGTH"], 0.5)  # default
        self.assertEqual(result["configs"]["c"]["AIM_STRENGTH"], 0.5)  # None treated as missing


class DefaultProfileCanonicalTests(unittest.TestCase):
    def test_default_shared_settings_have_game_resolution(self) -> None:
        shared = default_profile()["app"]["shared"]
        self.assertEqual(shared["game_resolution"], {"width": 1600, "height": 1200})
        self.assertTrue(shared["game_resolution_stretched"])

    def test_default_profile_has_no_safety_settings(self) -> None:
        self.assertNotIn("safety", default_profile()["app"])

    def test_default_cv_trigger_has_no_capture_settings(self) -> None:
        cv = default_profile()["components"]["cv_trigger"]
        self.assertNotIn("monitor", cv)
        self.assertNotIn("game_resolution", cv)

    def test_default_has_curve_library(self) -> None:
        cv = default_profile()["components"]["cv_trigger"]
        self.assertIn("aim_curves", cv)
        self.assertIn("linear", cv["aim_curves"])
        self.assertIn("exponential", cv["aim_curves"])

    def test_default_rules_have_scalar_aim_strength(self) -> None:
        cv = default_profile()["components"]["cv_trigger"]
        for name, rule in cv["configs"].items():
            with self.subTest(rule=name):
                self.assertIsInstance(rule["AIM_STRENGTH"], (int, float), f"{name}: AIM_STRENGTH is not numeric")
                self.assertGreaterEqual(rule["AIM_STRENGTH"], 0.0, f"{name}: AIM_STRENGTH < 0.0")

    def test_default_rules_have_aim_curve_id(self) -> None:
        cv = default_profile()["components"]["cv_trigger"]
        for name, rule in cv["configs"].items():
            with self.subTest(rule=name):
                self.assertIn("AIM_CURVE_ID", rule, f"{name} missing AIM_CURVE_ID")
                self.assertIn(rule["AIM_CURVE_ID"], _PRESET_CURVES, f"{name}: unknown curve {rule['AIM_CURVE_ID']}")

    def test_default_rules_have_max_aim_speed_px(self) -> None:
        cv = default_profile()["components"]["cv_trigger"]
        for name, rule in cv["configs"].items():
            with self.subTest(rule=name):
                self.assertIn("MAX_AIM_SPEED_PX", rule, f"{name} missing MAX_AIM_SPEED_PX")
                self.assertIsInstance(rule["MAX_AIM_SPEED_PX"], int)

    def test_default_rules_have_no_legacy_curve_keys(self) -> None:
        cv = default_profile()["components"]["cv_trigger"]
        legacy_keys = {"RESPONSE_CURVE", "CURVE_INTENSITY", "CONSTANT_SPEED_PX", "ACCEL_BOOST", "ANTI_OVERSHOOT"}
        for name, rule in cv["configs"].items():
            for key in legacy_keys:
                with self.subTest(rule=name, key=key):
                    self.assertNotIn(key, rule, f"{name}: legacy key {key} present in defaults")

    def test_default_rules_have_noise_and_snap(self) -> None:
        cv = default_profile()["components"]["cv_trigger"]
        for name, rule in cv["configs"].items():
            self.assertIn("NOISE_AMOUNT", rule, f"{name} missing NOISE_AMOUNT")
            self.assertIn("SNAP_DISTANCE", rule, f"{name} missing SNAP_DISTANCE")
            self.assertIn("SMOOTHING_ALPHA", rule, f"{name} missing SMOOTHING_ALPHA")

    def test_default_rules_have_priority(self) -> None:
        cv = default_profile()["components"]["cv_trigger"]
        for name, rule in cv["configs"].items():
            with self.subTest(rule=name):
                self.assertEqual(rule["priority"], 0)


class CheckedInProfileCanonicalTests(unittest.TestCase):
    """Validate profiles/Default.json against canonical format."""

    profile: dict[str, Any] = {}
    cv: dict[str, Any] = {}
    configs: dict[str, Any] = {}

    def setUp(self) -> None:
        profile_path = Path(__file__).resolve().parents[1] / "profiles" / "Default.json"
        with profile_path.open("r", encoding="utf-8") as f:
            self.profile = json.load(f)
        self.cv = self.profile.get("components", {}).get("cv_trigger", {})
        self.configs = self.cv.get("configs", {})

    def test_shared_settings_have_game_resolution(self) -> None:
        shared = self.profile.get("app", {}).get("shared", {})
        self.assertEqual(shared.get("game_resolution"), {"width": 1600, "height": 1200})
        self.assertTrue(shared.get("game_resolution_stretched"))

    def test_checked_in_profile_has_no_safety_settings(self) -> None:
        self.assertNotIn("safety", self.profile.get("app", {}))

    def test_cv_trigger_has_no_capture_settings(self) -> None:
        self.assertNotIn("monitor", self.cv)
        self.assertNotIn("game_resolution", self.cv)

    def test_has_curve_library(self) -> None:
        self.assertIn("aim_curves", self.cv)
        self.assertIn("linear", self.cv["aim_curves"])
        self.assertIn("exponential", self.cv["aim_curves"])

    def test_rules_have_scalar_aim_strength(self) -> None:
        for name, rule in self.configs.items():
            with self.subTest(rule=name):
                val = rule["AIM_STRENGTH"]
                self.assertIsInstance(val, (int, float), f"{name}: AIM_STRENGTH={val!r} is not numeric")
                self.assertGreaterEqual(val, 0.0, f"{name}: AIM_STRENGTH={val} < 0.0")

    def test_rules_have_valid_aim_curve_id(self) -> None:
        curve_library = self.cv.get("aim_curves", {})
        for name, rule in self.configs.items():
            with self.subTest(rule=name):
                cid = rule.get("AIM_CURVE_ID", "")
                self.assertIn(cid, curve_library, f"{name}: unknown curve id {cid!r}")

    def test_rules_have_max_aim_speed_px(self) -> None:
        for name, rule in self.configs.items():
            with self.subTest(rule=name):
                self.assertIn("MAX_AIM_SPEED_PX", rule, f"{name} missing MAX_AIM_SPEED_PX")
                self.assertIsInstance(rule["MAX_AIM_SPEED_PX"], (int, float))

    def test_no_legacy_curve_keys_in_rules(self) -> None:
        legacy_keys = {"RESPONSE_CURVE", "CURVE_INTENSITY", "CONSTANT_SPEED_PX", "ACCEL_BOOST", "ANTI_OVERSHOOT"}
        for name, rule in self.configs.items():
            for key in legacy_keys:
                with self.subTest(rule=name, key=key):
                    self.assertNotIn(key, rule, f"{name}: legacy key {key} present")

    def test_rules_have_noise_amount(self) -> None:
        for name, rule in self.configs.items():
            with self.subTest(rule=name):
                self.assertIn("NOISE_AMOUNT", rule, f"{name} missing NOISE_AMOUNT")

    def test_rules_have_snap_distance(self) -> None:
        for name, rule in self.configs.items():
            with self.subTest(rule=name):
                self.assertIn("SNAP_DISTANCE", rule, f"{name} missing SNAP_DISTANCE")

    def test_rules_have_priority(self) -> None:
        for name, rule in self.configs.items():
            with self.subTest(rule=name):
                self.assertIsInstance(rule.get("priority"), int, f"{name} missing integer priority")


if __name__ == "__main__":
    _ = unittest.main()
