from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.optional_dependency_stubs import install_mss_stub

install_mss_stub()

from app.components.cv_trigger.weapon_recoil import (
    PostShotTimingConfig,
    WeaponRecoilInfo,
    hold_restore_timing_ms,
    load_weapon_recoil_table,
    weapon_recoil_info,
)


class WeaponRecoilDataTests(unittest.TestCase):
    def test_loads_real_csv_and_canonical_weapon_lookup(self) -> None:
        table = load_weapon_recoil_table(Path("resources/cs2_weapon_fire_rate_recoil.csv"))

        deagle = weapon_recoil_info(table, "weapon_deagle")
        usp = weapon_recoil_info(table, "weapon_usp_silencer")

        self.assertIsNotNone(deagle)
        self.assertIsNotNone(usp)
        assert deagle is not None
        assert usp is not None
        self.assertEqual(deagle.weapon_name, "Desert Eagle")
        self.assertAlmostEqual(deagle.fire_rate_rpm, 266.666667)
        self.assertAlmostEqual(deagle.recoil_amount, 48.2)
        self.assertEqual(usp.weapon_code, "weapon_usp_silencer")

    def test_fire_interval_is_context_not_recovery_duration(self) -> None:
        info = WeaponRecoilInfo(
            weapon_name="Desert Eagle",
            weapon_code="weapon_deagle",
            fire_rate_rpm=266.666667,
            recoil_amount=48.2,
        )

        hold_ms, restore_ms = hold_restore_timing_ms(info, PostShotTimingConfig())

        self.assertAlmostEqual(info.fire_interval_ms, 225.0, delta=0.1)
        self.assertNotEqual(hold_ms + restore_ms, round(info.fire_interval_ms))
        self.assertGreater(hold_ms, 0)
        self.assertGreater(restore_ms, 0)

    def test_malformed_rows_are_skipped_and_missing_file_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "weapons.csv"
            path.write_text(
                "weapon_name,weapon_code,fire_rate_rpm,recoil_amount\n"
                "Bad,weapon_bad,nope,12\n"
                "Also Bad,weapon_bad2,120,nope\n"
                "Good,weapon_good,600,30\n",
                encoding="utf-8",
            )

            table = load_weapon_recoil_table(path)

        self.assertIsNone(weapon_recoil_info(table, "weapon_bad"))
        self.assertIsNone(weapon_recoil_info(table, "weapon_bad2"))
        self.assertIsNotNone(weapon_recoil_info(table, "weapon_good"))
        self.assertEqual(load_weapon_recoil_table(Path("/missing/cs2_weapon_fire_rate_recoil.csv")), {})

    def test_unknown_weapon_uses_configured_fallback_timing(self) -> None:
        config = PostShotTimingConfig(fallback_hold_ms=111, fallback_restore_ms=222)

        self.assertEqual(hold_restore_timing_ms(None, config), (111, 222))

    def test_recoil_amount_changes_timing_with_clamps(self) -> None:
        config = PostShotTimingConfig(
            recoil_hold_ms_per_amount=1.0,
            recoil_restore_ms_per_amount=0.5,
            fire_interval_hold_fraction=0.0,
            fire_interval_restore_fraction=0.0,
            min_hold_ms=50,
            max_hold_ms=240,
            min_restore_ms=80,
            max_restore_ms=260,
        )
        low = WeaponRecoilInfo("Glock", "weapon_glock", 400.0, 18.0)
        high = WeaponRecoilInfo("MAG-7", "weapon_mag7", 70.588235, 165.0)

        low_timing = hold_restore_timing_ms(low, config)
        high_timing = hold_restore_timing_ms(high, config)

        self.assertEqual(low_timing, (50, 80))
        self.assertEqual(high_timing, (165, 82))

    def test_fire_rate_contribution_to_timing_is_configurable(self) -> None:
        config = PostShotTimingConfig(
            recoil_hold_ms_per_amount=0.0,
            recoil_restore_ms_per_amount=0.0,
            fire_interval_hold_fraction=0.25,
            fire_interval_restore_fraction=0.50,
            min_hold_ms=0,
            max_hold_ms=1000,
            min_restore_ms=0,
            max_restore_ms=1000,
        )
        info = WeaponRecoilInfo("AK-47", "weapon_ak47", 600.0, 30.0)

        self.assertEqual(hold_restore_timing_ms(info, config), (25, 50))


if __name__ == "__main__":
    _ = unittest.main()
