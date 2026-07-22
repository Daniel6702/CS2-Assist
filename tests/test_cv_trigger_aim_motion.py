import unittest

from tests.optional_dependency_stubs import install_mss_stub

install_mss_stub()

from app.components.cv_trigger.aim_motion import (
    AimMotionConfig,
    compute_aim_motion,
    interpolate_curve,
)

LINEAR_CURVE: list[tuple[float, float]] = [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)]


class AimMotionCurveInvariantTests(unittest.TestCase):
    """Failing-first tests for the future aim_motion API (TDD red phase)."""

    # Helper ----------------------------------------------------------------

    def _cfg(
        self,
        aim_strength: float = 1.0,
        snap_distance: int = 200,
        max_aim_speed_px: int = 100,
        sens_mult_x: float = 1.0,
        sens_mult_y: float = 1.0,
        noise_px: float = 0.0,
        curve_points: list[tuple[float, float]] | None = None,
        anti_oscillation_radius_px: float = 0.0,
        anti_oscillation_reserve_counts: int = 0,
    ) -> AimMotionConfig:
        return AimMotionConfig(
            aim_strength=aim_strength,
            snap_distance=snap_distance,
            max_aim_speed_px=max_aim_speed_px,
            sens_mult_x=sens_mult_x,
            sens_mult_y=sens_mult_y,
            noise_px=noise_px,
            curve_points=list(LINEAR_CURVE if curve_points is None else curve_points),
            anti_oscillation_radius_px=anti_oscillation_radius_px,
            anti_oscillation_reserve_counts=anti_oscillation_reserve_counts,
        )

    # 1. Curve interpolation clamps x outside [0,1] -------------------------

    def test_interpolate_clamps_x_below_0(self) -> None:
        pts = [(0.0, 0.0), (1.0, 1.0)]
        self.assertEqual(interpolate_curve(pts, -0.5), 0.0)

    def test_interpolate_clamps_x_above_1(self) -> None:
        pts = [(0.0, 0.0), (1.0, 1.0)]
        self.assertEqual(interpolate_curve(pts, 1.5), 1.0)

    def test_interpolate_linear_midpoint(self) -> None:
        self.assertAlmostEqual(interpolate_curve([(0., 0.), (1., 1.)], 0.5), 0.5)

    def test_interpolate_multi_point_segment(self) -> None:
        pts = [(0.0, 0.0), (0.3, 0.1), (0.7, 0.6), (1.0, 1.0)]
        self.assertAlmostEqual(interpolate_curve(pts, 0.3), 0.1)
        self.assertAlmostEqual(interpolate_curve(pts, 0.5), 0.35)

    def test_interpolate_exact_endpoints(self) -> None:
        pts = [(0.0, 0.2), (0.5, 0.5), (1.0, 0.9)]
        self.assertAlmostEqual(interpolate_curve(pts, 0.0), 0.2)
        self.assertAlmostEqual(interpolate_curve(pts, 1.0), 0.9)

    # 2. Scalar Aim Strength 0, <1, 1, >1 -----------------------------------

    def test_aim_strength_zero_yields_no_movement(self) -> None:
        r = compute_aim_motion((50.0, 30.0), self._cfg(aim_strength=0.0))
        self.assertEqual((r.dx, r.dy), (0, 0))

    def test_aim_strength_below_one_produces_movement(self) -> None:
        r = compute_aim_motion((100.0, 60.0), self._cfg(aim_strength=0.5))
        self.assertNotEqual((r.dx, r.dy), (0, 0))

    def test_aim_strength_at_one_produces_movement(self) -> None:
        r = compute_aim_motion((100.0, 60.0), self._cfg(aim_strength=1.0))
        self.assertNotEqual((r.dx, r.dy), (0, 0))

    def test_aim_strength_above_one_produces_movement(self) -> None:
        r = compute_aim_motion((100.0, 60.0), self._cfg(aim_strength=2.0))
        self.assertNotEqual((r.dx, r.dy), (0, 0))

    def test_aim_strength_above_one_bounded_by_distance(self) -> None:
        r = compute_aim_motion((5.0, 5.0), self._cfg(aim_strength=10.0))
        self.assertLessEqual(abs(r.dx), 5)
        self.assertLessEqual(abs(r.dy), 5)

    # 4. Zero movement outside snap distance --------------------------------

    def test_zero_movement_outside_snap_distance(self) -> None:
        r = compute_aim_motion((100.0, 0.0), self._cfg(snap_distance=50))
        self.assertEqual((r.dx, r.dy), (0, 0))

    def test_movement_inside_snap_distance(self) -> None:
        r = compute_aim_motion((50.0, 0.0), self._cfg(snap_distance=50))
        self.assertNotEqual((r.dx, r.dy), (0, 0))

    def test_zero_movement_when_error_is_zero(self) -> None:
        r = compute_aim_motion((0.0, 0.0), self._cfg())
        self.assertEqual((r.dx, r.dy), (0, 0))

    # 5. Movement never points away from target -----------------------------

    def test_movement_toward_positive_error(self) -> None:
        r = compute_aim_motion((50.0, 30.0), self._cfg())
        self.assertGreaterEqual(r.dx, 0)
        self.assertGreaterEqual(r.dy, 0)

    def test_movement_toward_negative_error(self) -> None:
        r = compute_aim_motion((-50.0, -30.0), self._cfg())
        self.assertLessEqual(r.dx, 0)
        self.assertLessEqual(r.dy, 0)

    def test_movement_toward_mixed_sign_error(self) -> None:
        r = compute_aim_motion((50.0, -30.0), self._cfg())
        self.assertGreaterEqual(r.dx, 0)
        self.assertLessEqual(r.dy, 0)

    # 6. Movement magnitude bounded by remaining distance -------------------

    def test_movement_x_bounded_by_error(self) -> None:
        r = compute_aim_motion((10.0, 5.0), self._cfg(sens_mult_x=1.0))
        self.assertLessEqual(abs(r.dx), 10)
        self.assertLessEqual(abs(r.dy), 5)

    def test_movement_bounded_with_sensitivity_scaling(self) -> None:
        r = compute_aim_motion((10.0, 20.0), self._cfg(sens_mult_x=2.0, sens_mult_y=0.5))
        self.assertLessEqual(abs(r.dx), abs(round(10.0 * 2.0)))
        self.assertLessEqual(abs(r.dy), abs(round(20.0 * 0.5)))

    def test_movement_bounded_extreme_strength(self) -> None:
        r = compute_aim_motion((5.0, 5.0), self._cfg(aim_strength=100.0, sens_mult_x=3.0))
        self.assertLessEqual(abs(r.dx), abs(round(5.0 * 3.0)))
        self.assertLessEqual(abs(r.dy), abs(round(5.0 * 3.0)))

    def test_movement_bounded_asymmetric_error(self) -> None:
        r = compute_aim_motion((3.0, 30.0), self._cfg(sens_mult_x=1.5, sens_mult_y=1.0))
        self.assertLessEqual(abs(r.dx), abs(round(3.0 * 1.5)))
        self.assertLessEqual(abs(r.dy), abs(round(30.0 * 1.0)))

    # 7. Rounded integer output never flips sign ----------------------------

    def test_small_positive_error_not_negative(self) -> None:
        r = compute_aim_motion((0.3, 0.0), self._cfg(aim_strength=0.1))
        self.assertGreaterEqual(r.dx, 0)

    def test_small_negative_error_not_positive(self) -> None:
        r = compute_aim_motion((-0.3, 0.0), self._cfg(aim_strength=0.1))
        self.assertLessEqual(r.dx, 0)

    def test_zero_error_stays_zero(self) -> None:
        r = compute_aim_motion((0.0, 0.0), self._cfg())
        self.assertEqual((r.dx, r.dy), (0, 0))

    # 8. Noise cannot create target crossing --------------------------------

    def test_noise_does_not_cross_target(self) -> None:
        r = compute_aim_motion((8.0, 8.0), self._cfg(noise_px=5.0))
        self.assertLessEqual(abs(r.dx), 8)
        self.assertLessEqual(abs(r.dy), 8)
        self.assertGreaterEqual(r.dx, 0)
        self.assertGreaterEqual(r.dy, 0)

    def test_deterministic_max_noise_safe(self) -> None:
        r = compute_aim_motion((5.0, 5.0), self._cfg(noise_px=3.0), noise_rng=lambda lo, hi: hi)
        self.assertLessEqual(abs(r.dx), 5)
        self.assertLessEqual(abs(r.dy), 5)

    def test_noise_direction_preserved(self) -> None:
        r = compute_aim_motion((-10.0, -10.0), self._cfg(noise_px=2.0), noise_rng=lambda lo, hi: lo)
        self.assertLessEqual(r.dx, 0)
        self.assertLessEqual(r.dy, 0)

    # 9. Near-target: arrive or stop instead of oscillate -------------------

    def test_near_target_arrives(self) -> None:
        r = compute_aim_motion((0.5, 0.3), self._cfg())
        if r.arrived:
            self.assertEqual(r.dx, round(0.5))
            self.assertEqual(r.dy, round(0.3))
        else:
            self.assertEqual((r.dx, r.dy), (0, 0))

    def test_zero_error_arrives(self) -> None:
        r = compute_aim_motion((0.0, 0.0), self._cfg())
        self.assertTrue(r.arrived)
        self.assertEqual((r.dx, r.dy), (0, 0))

    def test_near_target_no_oscillation(self) -> None:
        r = compute_aim_motion((0.7, 0.0), self._cfg(aim_strength=0.5))
        self.assertEqual(
            r,
            compute_aim_motion((0.7, 0.0), self._cfg(aim_strength=0.5)),
        )

    def test_tiny_error_does_not_cross(self) -> None:
        for ex, ey in [(0.1, 0.0), (0.0, 0.2), (0.1, 0.1), (-0.1, 0.1)]:
            r = compute_aim_motion((ex, ey), self._cfg())
            self.assertLessEqual(abs(r.dx), max(1, abs(round(ex))))
            self.assertLessEqual(abs(r.dy), max(1, abs(round(ey))))

    def test_raw_limit_rejects_stale_smoothed_direction(self) -> None:
        r = compute_aim_motion(
            (40.0, 0.0),
            self._cfg(aim_strength=10.0, max_aim_speed_px=100),
            limit_error_px=(-3.0, 0.0),
        )

        self.assertEqual(r.dx, 0)
        self.assertEqual(r.dy, 0)

    def test_raw_limit_uses_floor_not_round_near_target(self) -> None:
        r = compute_aim_motion(
            (50.0, 0.0),
            self._cfg(aim_strength=10.0, max_aim_speed_px=100, sens_mult_x=1.0),
            limit_error_px=(0.9, 0.0),
        )

        self.assertEqual(r.dx, 0)
        self.assertTrue(r.arrived)

    def test_raw_limit_caps_aggressive_curve_without_slowing_safe_steps(self) -> None:
        cfg = self._cfg(
            aim_strength=100.0,
            max_aim_speed_px=1000,
            curve_points=[(0.0, 1.0), (1.0, 1.0)],
        )

        safe = compute_aim_motion((50.0, 0.0), cfg, limit_error_px=(25.0, 0.0))
        capped = compute_aim_motion((50.0, 0.0), cfg, limit_error_px=(7.0, 0.0))

        self.assertEqual(safe.dx, 25)
        self.assertEqual(capped.dx, 7)

    def test_closed_loop_raw_limiter_never_crosses_target(self) -> None:
        cfg = self._cfg(
            aim_strength=100.0,
            max_aim_speed_px=1000,
            noise_px=20.0,
            curve_points=[(0.0, 1.0), (1.0, 1.0)],
        )
        error = 6.4

        for _ in range(20):
            previous = error
            r = compute_aim_motion(
                (50.0, 0.0),
                cfg,
                noise_rng=lambda lo, hi: hi,
                limit_error_px=(error, 0.0),
            )
            error -= r.dx
            self.assertGreaterEqual(previous * error, 0.0)
            self.assertLessEqual(abs(error), abs(previous))

        self.assertGreaterEqual(error, 0.0)

    def test_anti_oscillation_reserve_leaves_near_target_count_margin(self) -> None:
        cfg = self._cfg(
            aim_strength=100.0,
            max_aim_speed_px=1000,
            curve_points=[(0.0, 1.0), (1.0, 1.0)],
            anti_oscillation_radius_px=24.0,
            anti_oscillation_reserve_counts=1,
        )

        r = compute_aim_motion((50.0, 0.0), cfg, limit_error_px=(6.0, 0.0))

        self.assertEqual(r.dx, 5)
        self.assertFalse(r.arrived)

    def test_anti_oscillation_reserve_does_not_slow_far_target_steps(self) -> None:
        cfg = self._cfg(
            aim_strength=100.0,
            max_aim_speed_px=1000,
            curve_points=[(0.0, 1.0), (1.0, 1.0)],
            anti_oscillation_radius_px=24.0,
            anti_oscillation_reserve_counts=1,
        )

        r = compute_aim_motion((50.0, 0.0), cfg, limit_error_px=(40.0, 0.0))

        self.assertEqual(r.dx, 40)


if __name__ == "__main__":
    _ = unittest.main()
