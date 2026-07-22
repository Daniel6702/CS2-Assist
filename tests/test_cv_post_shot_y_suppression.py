from __future__ import annotations

import unittest

from tests.optional_dependency_stubs import install_mss_stub

install_mss_stub()

from app.components.cv_trigger.post_shot_y import (
    PostShotSuppressionConfig,
    PostShotYSuppression,
    ShotEventTracker,
    ShotStartKind,
    clamp_positive_y_to_limit,
    post_shot_config_from_mapping,
)
from app.components.cv_trigger.weapon_recoil import WeaponRecoilInfo
from app.components.cv_trigger.core import _should_note_manual_release_candidate


DEAGLE = WeaponRecoilInfo("Desert Eagle", "weapon_deagle", 266.666667, 48.2)
AK = WeaponRecoilInfo("AK-47", "weapon_ak47", 600.0, 30.0)
MAG7 = WeaponRecoilInfo("MAG-7", "weapon_mag7", 70.588235, 165.0)


class ProvisionalShotTrackerTests(unittest.TestCase):
    def test_manual_release_candidate_is_allowed_for_short_tap(self) -> None:
        self.assertTrue(
            _should_note_manual_release_candidate(
                pressed_at=1.00,
                released_at=1.20,
                max_hold_seconds=0.30,
            ),
        )

    def test_manual_release_candidate_is_blocked_after_long_hold(self) -> None:
        self.assertFalse(
            _should_note_manual_release_candidate(
                pressed_at=1.00,
                released_at=1.31,
                max_hold_seconds=0.30,
            ),
        )

    def test_manual_press_starts_provisional_suppression_before_gsi_confirmation(self) -> None:
        tracker = ShotEventTracker(PostShotSuppressionConfig(candidate_validation_window_ms=300))
        suppressor = PostShotYSuppression(PostShotSuppressionConfig(stabilization_strength=0.90))

        tracker.update_gsi_weapon_ammo("weapon_deagle", 7, 7, now=0.90)
        event = tracker.note_manual_press("weapon_deagle", now=1.00)
        suppressor.start(event, DEAGLE)

        self.assertEqual(event.kind, ShotStartKind.PROVISIONAL)
        self.assertAlmostEqual(suppressor.apply_y(20.0, now=1.01, recoil_active=False), 2.36)
        self.assertEqual(suppressor.apply_y(-12.0, now=1.01, recoil_active=False), -12.0)
        self.assertEqual(suppressor.apply_y(0.0, now=1.01, recoil_active=False), 0.0)

    def test_same_weapon_ammo_decrease_confirms_pending_shot(self) -> None:
        tracker = ShotEventTracker(PostShotSuppressionConfig(candidate_validation_window_ms=300))

        tracker.update_gsi_weapon_ammo("weapon_deagle", 7, 7, now=0.90)
        provisional = tracker.note_manual_press("weapon_deagle", now=1.00)
        update = tracker.update_gsi_weapon_ammo("weapon_deagle", 6, 7, now=1.06)

        self.assertIsNotNone(update.confirmed)
        assert update.confirmed is not None
        self.assertEqual(update.confirmed.confirmed_from.kind, ShotStartKind.PROVISIONAL)
        self.assertEqual(update.confirmed.confirmed_from.source, provisional.source)
        self.assertTrue(update.confirmed.first_in_mag)
        self.assertTrue(update.should_start_suppression)
        self.assertFalse(update.cancel_provisional)

    def test_cv_auto_click_can_start_provisional_suppression(self) -> None:
        tracker = ShotEventTracker(PostShotSuppressionConfig(candidate_validation_window_ms=300))

        tracker.update_gsi_weapon_ammo("weapon_deagle", 7, 7, now=0.90)
        provisional = tracker.note_cv_auto_click("weapon_deagle", now=1.00)
        update = tracker.update_gsi_weapon_ammo("weapon_deagle", 6, 7, now=1.04)

        self.assertEqual(provisional.source, "cv_auto")
        self.assertIsNotNone(update.confirmed)
        assert update.confirmed is not None
        self.assertEqual(update.confirmed.confirmed_from.source, "cv_auto")

    def test_dry_fire_or_stale_validation_cancels_provisional_state(self) -> None:
        tracker = ShotEventTracker(PostShotSuppressionConfig(candidate_validation_window_ms=100))

        tracker.update_gsi_weapon_ammo("weapon_deagle", 0, 7, now=0.90)
        tracker.note_manual_press("weapon_deagle", now=1.00)
        update = tracker.update_gsi_weapon_ammo("weapon_deagle", 0, 7, now=1.20)

        self.assertIsNone(update.confirmed)
        self.assertTrue(update.cancel_provisional)

    def test_reload_and_weapon_change_cancel_pending_state(self) -> None:
        tracker = ShotEventTracker(PostShotSuppressionConfig(candidate_validation_window_ms=300))

        tracker.update_gsi_weapon_ammo("weapon_deagle", 1, 7, now=0.90)
        tracker.note_manual_press("weapon_deagle", now=1.00)
        reload_update = tracker.update_gsi_weapon_ammo("weapon_deagle", 7, 7, now=1.02)
        tracker.note_manual_press("weapon_deagle", now=1.10)
        switch_update = tracker.update_gsi_weapon_ammo("weapon_ak47", 30, 30, now=1.12)

        self.assertTrue(reload_update.cancel_provisional)
        self.assertTrue(switch_update.cancel_provisional)

    def test_sustained_recoil_active_decrease_does_not_start_duplicate_suppression(self) -> None:
        tracker = ShotEventTracker(PostShotSuppressionConfig(candidate_validation_window_ms=300, sustained_shot_index=2))

        tracker.update_gsi_weapon_ammo("weapon_ak47", 30, 30, now=0.90)
        tracker.note_manual_press("weapon_ak47", now=1.00)
        first = tracker.update_gsi_weapon_ammo("weapon_ak47", 29, 30, now=1.04, recoil_active=False)
        sustained = tracker.update_gsi_weapon_ammo("weapon_ak47", 28, 30, now=1.14, recoil_active=True)

        self.assertTrue(first.should_start_suppression)
        self.assertIsNotNone(sustained.confirmed)
        self.assertFalse(sustained.should_start_suppression)
        assert sustained.confirmed is not None
        self.assertTrue(sustained.confirmed.sustained)


class PostShotYSuppressionTests(unittest.TestCase):
    def test_default_enabled_config_nearly_blocks_downward_y(self) -> None:
        config = PostShotSuppressionConfig(enabled=True)
        suppressor = PostShotYSuppression(config)
        event = ShotEventTracker(config).note_manual_press("weapon_deagle", now=1.00)

        suppressor.start(event, DEAGLE)

        self.assertLessEqual(suppressor.apply_y(20.0, now=1.01, recoil_active=False), 0.5)
        self.assertEqual(suppressor.apply_y(-20.0, now=1.01, recoil_active=False), -20.0)

    def test_weapon_recoil_controls_stabilization_duration(self) -> None:
        config = PostShotSuppressionConfig(enabled=True, stabilization_strength=1.0)
        deagle = PostShotYSuppression(config)
        mag7 = PostShotYSuppression(config)
        event = ShotEventTracker(config).note_manual_press("weapon_deagle", now=1.00)

        deagle.start(event, DEAGLE)
        mag7.start(event, MAG7)

        self.assertFalse(deagle.active_at(1.35))
        self.assertTrue(mag7.active_at(1.35))

    def test_config_accepts_strength_above_old_ui_ceiling(self) -> None:
        config = post_shot_config_from_mapping({"enabled": True, "stabilization_strength": 4.0})

        self.assertEqual(config.stabilization_strength, 4.0)

    def test_high_recoil_strength_above_old_cap_extends_weapon_window(self) -> None:
        config = PostShotSuppressionConfig(enabled=True, stabilization_strength=4.0)
        suppressor = PostShotYSuppression(config)
        event = ShotEventTracker(config).note_manual_press("weapon_mag7", now=1.00)

        suppressor.start(event, MAG7)

        self.assertTrue(suppressor.active_at(2.20))
        self.assertEqual(suppressor.apply_y(20.0, now=2.20, recoil_active=False), 0.0)

    def test_high_recoil_automatic_keeps_y_guard_through_early_spray(self) -> None:
        config = PostShotSuppressionConfig(enabled=True, stabilization_strength=1.50)
        suppressor = PostShotYSuppression(config)
        event = ShotEventTracker(config).note_manual_press("weapon_ak47", now=1.00)

        suppressor.start(event, AK)

        self.assertTrue(suppressor.active_at(1.30))
        self.assertLessEqual(suppressor.apply_y(20.0, now=1.30, recoil_active=False), 0.5)

    def test_horizontal_strength_reduces_left_and_right_x_during_weapon_window(self) -> None:
        config = PostShotSuppressionConfig(
            enabled=True,
            stabilization_strength=1.0,
            horizontal_stabilization_strength=0.50,
        )
        suppressor = PostShotYSuppression(config)
        event = ShotEventTracker(config).note_manual_press("weapon_ak47", now=1.00)

        suppressor.start(event, AK)

        self.assertAlmostEqual(suppressor.apply_x(20.0, now=1.05), 10.2)
        self.assertAlmostEqual(suppressor.apply_x(-20.0, now=1.05), -10.2)
        self.assertLessEqual(suppressor.apply_y(20.0, now=1.05, recoil_active=False), 0.5)

    def test_zero_horizontal_strength_leaves_x_unchanged_while_y_is_guarded(self) -> None:
        config = PostShotSuppressionConfig(
            enabled=True,
            stabilization_strength=1.0,
            horizontal_stabilization_strength=0.0,
        )
        suppressor = PostShotYSuppression(config)
        event = ShotEventTracker(config).note_manual_press("weapon_ak47", now=1.00)

        suppressor.start(event, AK)

        self.assertEqual(suppressor.apply_x(20.0, now=1.05), 20.0)
        self.assertEqual(suppressor.apply_x(-20.0, now=1.05), -20.0)
        self.assertLessEqual(suppressor.apply_y(20.0, now=1.05, recoil_active=False), 0.5)

    def test_stabilization_strength_scales_reduction_and_duration(self) -> None:
        config = PostShotSuppressionConfig(
            stabilization_strength=0.50,
            fallback_hold_ms=100,
            fallback_restore_ms=100,
        )
        suppressor = PostShotYSuppression(config)
        event = ShotEventTracker(config).note_manual_press("weapon_deagle", now=1.00)

        suppressor.start(event, None)

        self.assertAlmostEqual(suppressor.apply_y(20.0, now=1.05, recoil_active=False), 10.2)
        self.assertTrue(suppressor.active_at(1.09))
        self.assertFalse(suppressor.active_at(1.11))
        self.assertEqual(suppressor.apply_y(-20.0, now=1.15, recoil_active=False), -20.0)
        self.assertEqual(suppressor.apply_y(20.0, now=1.11, recoil_active=False), 20.0)

    def test_recoil_active_cap_limits_downward_y_without_new_window(self) -> None:
        config = PostShotSuppressionConfig(
            enabled=True,
            stabilization_strength=0.50,
            recoil_active_downward_scale=0.05,
            fallback_hold_ms=100,
            fallback_restore_ms=100,
        )
        suppressor = PostShotYSuppression(config)
        event = ShotEventTracker(config).note_manual_press("weapon_ak47", now=1.00)

        suppressor.start(event, None)

        self.assertAlmostEqual(suppressor.apply_y(20.0, now=1.05, recoil_active=True), 1.0)

    def test_target_loss_does_not_cancel_active_recoil_guard(self) -> None:
        config = PostShotSuppressionConfig(stabilization_strength=10.0)
        suppressor = PostShotYSuppression(config)
        event = ShotEventTracker(config).note_manual_press("weapon_mag7", now=1.00)

        suppressor.start(event, MAG7)
        suppressor.note_target_missing(now=1.02)
        suppressor.note_target_missing(now=1.20)
        suppressor.note_target_missing(now=2.00)

        self.assertTrue(suppressor.active_at(2.00))
        self.assertEqual(suppressor.apply_y(20.0, now=2.00, recoil_active=False), 0.0)

    def test_positive_y_smoothing_cap_discards_blocked_movement(self) -> None:
        self.assertEqual(clamp_positive_y_to_limit(smoothed_y=20.0, limited_y=2.0), 2.0)
        self.assertEqual(clamp_positive_y_to_limit(smoothed_y=-8.0, limited_y=2.0), -8.0)
        self.assertEqual(clamp_positive_y_to_limit(smoothed_y=20.0, limited_y=0.0), 0.0)


if __name__ == "__main__":
    _ = unittest.main()
