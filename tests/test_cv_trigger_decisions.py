import unittest

from app.components.cv_trigger.core import (
    _aim_point_for_box,
    _auto_shoot_zone_contains_crosshair,
    _shot_cooldown_active,
)


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


if __name__ == "__main__":
    unittest.main()
