from __future__ import annotations

import unittest

from app.components.cv_trigger.curve_config import build_curve_library
from app.components.cv_trigger.runtime_rules import compile_rules, highest_priority_rules


class CVTriggerRuntimeRulesTests(unittest.TestCase):
    def test_compiled_rules_preserve_priority_weapon_scope_and_targets(self) -> None:
        rules = compile_rules(
            {
                "body": {
                    "enabled": True,
                    "priority": 0,
                    "activation": {"mode": "always"},
                    "allowed_weapons": ["weapon_ak47"],
                    "target_type": "type1",
                    "only_when_scoped_visual": False,
                    "auto_shoot": False,
                    "spray_target_offset_enabled": True,
                    "AIM_MODE": "body",
                    "HEAD_OFFSET": 0.1,
                    "BODY_KNEE_OFFSET": 0.5,
                    "SNAP_DISTANCE": 60,
                    "SETTLE_FRAMES": 2,
                    "CLICK_HOLD_MS": 20,
                    "COOLDOWN_MS": 350,
                    "auto_shoot_aim_cooldown_ms": 200,
                    "AIM_STRENGTH": 0.55,
                    "AIM_CURVE_ID": "linear",
                    "MAX_AIM_SPEED_PX": 30,
                    "SMOOTHING_ALPHA": 0.5,
                    "NOISE_AMOUNT": 1.0,
                    "AUTO_SHOOT_ZONE_WIDTH": 28,
                    "AUTO_SHOOT_ZONE_HEIGHT": 36,
                    "AUTO_SHOOT_ZONE_Y_POS": 0.35,
                },
                "head": {
                    "enabled": True,
                    "priority": 1,
                    "activation": {"device": "mouse", "button": "left"},
                    "allowed_weapons": ["weapon_ak47"],
                    "target_type": "type2",
                    "only_when_scoped_visual": True,
                    "auto_shoot": True,
                    "spray_target_offset_enabled": False,
                    "AIM_MODE": "head",
                    "HEAD_OFFSET": 0.1,
                    "BODY_KNEE_OFFSET": 0.5,
                    "SNAP_DISTANCE": 100,
                    "SETTLE_FRAMES": 2,
                    "CLICK_HOLD_MS": 15,
                    "COOLDOWN_MS": 250,
                    "auto_shoot_aim_cooldown_ms": 250,
                    "AIM_STRENGTH": 0.9,
                    "AIM_CURVE_ID": "linear",
                    "MAX_AIM_SPEED_PX": 35,
                    "SMOOTHING_ALPHA": 0.5,
                    "NOISE_AMOUNT": 1.0,
                    "AUTO_SHOOT_ZONE_WIDTH": 28,
                    "AUTO_SHOOT_ZONE_HEIGHT": 36,
                    "AUTO_SHOOT_ZONE_Y_POS": 0.35,
                },
            },
            build_curve_library(),
        )

        active = highest_priority_rules([rules["body"], rules["head"]])

        self.assertEqual([rule.name for rule in active], ["head"])
        self.assertTrue(rules["body"].weapon_allowed("weapon_ak47"))
        self.assertFalse(rules["body"].weapon_allowed("weapon_deagle"))
        self.assertFalse(rules["head"].scope_allowed(False))
        self.assertEqual(rules["body"].target_classes({"t", "ct"}), {0, 2})
        self.assertEqual(rules["head"].target_classes({"t", "ct"}), {1, 3})
        self.assertEqual(rules["head"].snap_radius_sq, 10_000)

    def test_malformed_curve_falls_back_to_linear(self) -> None:
        rules = compile_rules(
            {
                "bad_curve": {
                    "AIM_MODE": "head",
                    "HEAD_OFFSET": 0.1,
                    "SNAP_DISTANCE": 60,
                    "SETTLE_FRAMES": 1,
                    "CLICK_HOLD_MS": 1,
                    "COOLDOWN_MS": 1,
                    "AIM_CURVE_ID": "broken",
                }
            },
            {"broken": {"points": [["bad"]]}},
        )
        expected = tuple((float(point[0]), float(point[1])) for point in build_curve_library()["linear"]["points"])

        self.assertEqual(rules["bad_curve"].curve_points, expected)


if __name__ == "__main__":
    _ = unittest.main()
