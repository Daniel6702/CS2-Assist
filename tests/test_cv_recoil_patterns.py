from __future__ import annotations

import unittest

from tests.optional_dependency_stubs import install_mss_stub, install_pynput_stub

install_mss_stub()
install_pynput_stub()

from app.components.cv_trigger.patterns import _scaled_recoil_pattern_steps, resolve_pattern_name
from app.components.recoil import RuntimeSettings, parse_pattern


class CvRecoilPatternTests(unittest.TestCase):
    def test_gsi_weapon_name_resolves_exact_pattern_key(self) -> None:
        pattern_file = {
            "patterns": {
                "weapon_ak47": {
                    "scale_x": 1.0,
                    "scale_y": 1.0,
                    "steps": [{"dx": 1.5, "dy": -2.25, "duration_ms": 9}],
                },
            },
        }

        self.assertEqual(resolve_pattern_name(pattern_file, "weapon_ak47"), "weapon_ak47")

    def test_pattern_scale_is_applied_to_decimal_steps(self) -> None:
        pattern_file = {
            "patterns": {
                "weapon_ak47": {
                    "scale_x": 1.5,
                    "scale_y": 0.5,
                    "steps": [{"dx": 1.5, "dy": -2.25, "duration_ms": 9}],
                },
            },
        }
        recoil_sync = {
            "axis_strength_percent": {"x": 50.0, "y": 200.0},
            "sensitivity": {
                "enabled": False,
                "apply_to_axis": {"x": True, "y": True},
            },
        }

        steps = _scaled_recoil_pattern_steps(pattern_file, "weapon_ak47", recoil_sync, 1.0)

        self.assertEqual(steps, [(1.125, -2.25, 9)])

    def test_scale_one_uses_raw_decimal_steps(self) -> None:
        pattern_file = {
            "patterns": {
                "weapon_ak47": {
                    "scale_x": 1.0,
                    "scale_y": 1.0,
                    "steps": [{"dx": 1.5, "dy": -2.25, "duration_ms": 9}],
                },
            },
        }

        recoil_sync = {"sensitivity": {"enabled": False}}

        steps = _scaled_recoil_pattern_steps(pattern_file, "weapon_ak47", recoil_sync, 1.0)

        self.assertEqual(steps, [(1.5, -2.25, 9)])

    def test_recoil_parser_applies_pattern_scale_to_decimal_steps(self) -> None:
        pattern_file = {
            "patterns": {
                "weapon_ak47": {
                    "scale_x": 2.0,
                    "scale_y": 0.5,
                    "steps": [{"dx": 1.25, "dy": -3.5, "duration_ms": 11}],
                },
            },
        }
        settings = RuntimeSettings(
            x_strength_percent=50.0,
            y_strength_percent=25.0,
            sensitivity_enabled=False,
            reference_sens=2.52,
            program_sens=2.52,
            apply_x=True,
            apply_y=True,
            noise_strength_px=0.0,
            return_mouse_enabled=False,
            return_mouse_delay_ms=20,
            return_mouse_duration_ms=140,
            return_mouse_y_percent=100.0,
        )

        steps = parse_pattern(pattern_file, "weapon_ak47", settings)

        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].dx, 1.25)
        self.assertEqual(steps[0].dy, -0.4375)
        self.assertEqual(steps[0].duration_ms, 11)


if __name__ == "__main__":
    _ = unittest.main()
