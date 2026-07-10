import unittest
from pathlib import Path

from app.components.cv_trigger.core import (
    _aim_point_for_box,
    _auto_shoot_zone_contains_crosshair,
    _curve_points_for_rule,
    _shot_cooldown_active,
    _smoothed_error_for_rule,
)
from app.components.cv_trigger.curve_config import build_curve_library


class CVTriggerDecisionTests(unittest.TestCase):
    def test_auto_shoot_zone_ignores_snap_distance_and_aim_mode(self) -> None:
        box = (90, 90, 110, 130)
        crosshair = (100, 110)
        snap_distance = 5

        self.assertTrue(
            _auto_shoot_zone_contains_crosshair(
                box=box,
                crosshair=crosshair,
                cross_x=1,
                cross_y_top=1,
                cross_y_bot=1,
            )
        )
        head_x, head_y = _aim_point_for_box(
            box=box,
            crosshair=crosshair,
            aim_mode="head",
            head_offset=0.0,
            body_knee_offset=0.5,
        )
        aim_d2 = (head_x - crosshair[0]) * (head_x - crosshair[0]) + (head_y - crosshair[1]) * (head_y - crosshair[1])
        self.assertGreater(aim_d2, snap_distance * snap_distance)
        self.assertNotEqual(
            (head_x, head_y),
            _aim_point_for_box(box=box, crosshair=crosshair, aim_mode="body", head_offset=0.0, body_knee_offset=0.5),
        )

    def test_shot_cooldown_does_not_mean_aim_cooldown(self) -> None:
        self.assertTrue(_shot_cooldown_active(now=10.0, cooldown_until=11.0))

    def test_core_runtime_uses_pure_aim_motion_without_legacy_branches(self) -> None:
        source = Path("app/components/cv_trigger/core.py").read_text(encoding="utf-8")

        self.assertIn("aim_motion.compute_aim_motion", source)
        for forbidden in ("def _response_fraction", "curve_intensity", "constant_speed_px", "accel_boost"):
            self.assertNotIn(forbidden, source)

    def test_curve_points_fallback_to_linear_when_library_is_malformed(self) -> None:
        points = _curve_points_for_rule({"broken": {"points": [["bad"]]}}, "missing")
        expected = [(float(point[0]), float(point[1])) for point in build_curve_library()["linear"]["points"]]

        self.assertEqual(points, expected)

    def test_rule_smoothing_state_stays_outside_pure_motion_module(self) -> None:
        state: dict[str, tuple[float, float] | None] = {"rule": (10.0, -10.0)}

        smoothed = _smoothed_error_for_rule(
            rule_name="rule",
            error_px=(20.0, -20.0),
            smoothing_alpha=0.5,
            per_rule_smooth=state,
        )

        self.assertEqual(smoothed, (15.0, -15.0))
        self.assertEqual(state["rule"], smoothed)


if __name__ == "__main__":
    unittest.main()
