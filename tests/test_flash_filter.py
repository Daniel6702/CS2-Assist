from __future__ import annotations

import os
import sys
import unittest

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from app.components.flash_filter import FlashFilter, FlashFilterComponent  # noqa: E402
from app.defaults import default_profile  # noqa: E402
from app.gsi import GameState  # noqa: E402
from app.platform.xrandr import connected_outputs_from_query  # noqa: E402
from app.runtime import RuntimeManager  # noqa: E402
from app.ui.tabs.misc_tab import MiscTab  # noqa: E402


class FlashFilterParsingTests(unittest.TestCase):
    def test_connected_outputs_from_query_returns_connected_port_names(self) -> None:
        query = """
Screen 0: minimum 8 x 8, current 2560 x 1440, maximum 32767 x 32767
HDMI-0 disconnected
DP-0 disconnected
DP-2 connected primary 2560x1440+0+0 (normal left inverted right x axis y axis)
DP-3 connected 1920x1080+2560+0 (normal left inverted right x axis y axis)
"""

        outputs = connected_outputs_from_query(query)

        self.assertEqual(outputs, ["DP-2", "DP-3"])

    def test_game_state_reads_flashed_value(self) -> None:
        state = GameState.from_payload({"player": {"state": {"health": 100, "flashed": 128}}})

        self.assertTrue(state.flashed)

    def test_flash_filter_applies_and_restores_xrandr_state(self) -> None:
        commands: list[tuple[str, ...]] = []

        def fake_xrandr(*arguments: str) -> str:
            if arguments == ("--verbose",):
                return "DP-2 connected primary\n  Gamma: 1.0:1.0:1.0\n  Brightness: 1.0\n"
            commands.append(arguments)
            return ""

        flash_filter = FlashFilter(
            output="DP-2",
            brightness_factor=0.5,
            gamma_multipliers=(1.4, 1.2, 0.8),
            fade_seconds=0.05,
            update_hz=30.0,
            runner=fake_xrandr,
        )

        flash_filter.set_flashed(True)
        flash_filter.shutdown()

        self.assertEqual(commands[0], ("--output", "DP-2", "--gamma", "1.4000:1.2000:0.8000", "--brightness", "0.5000"))
        self.assertEqual(commands[-1], ("--output", "DP-2", "--gamma", "1.0000:1.0000:1.0000", "--brightness", "1.0000"))


class FlashFilterWiringTests(unittest.TestCase):
    def test_runtime_registers_flash_filter_component(self) -> None:
        runtime = RuntimeManager(status_callback=lambda _source, _message: None)

        self.assertIn("flash_filter", runtime.components)
        self.assertIsInstance(runtime.components["flash_filter"], FlashFilterComponent)

    def test_default_profile_contains_disabled_flash_filter_section(self) -> None:
        profile = default_profile()

        self.assertEqual(
            profile["components"]["flash_filter"],
            {
                "enabled": False,
                "output": "",
                "brightness_factor": 0.50,
                "gamma_red": 1.42,
                "gamma_green": 1.22,
                "gamma_blue": 0.80,
                "fade_seconds": 1.90,
                "update_hz": 30.0,
            },
        )

    def test_misc_tab_round_trips_flash_filter_config(self) -> None:
        tab = MiscTab()
        try:
            tab.load_config(
                "flash_filter",
                {
                    "enabled": True,
                    "output": "DP-2",
                    "brightness_factor": 0.35,
                    "gamma_red": 1.5,
                    "gamma_green": 1.2,
                    "gamma_blue": 0.7,
                    "fade_seconds": 2.5,
                },
            )

            extracted = tab.extract_config()["flash_filter"]
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()

        self.assertEqual(
            extracted,
            {
                "enabled": True,
                "output": "DP-2",
                "brightness_factor": 0.35,
                "gamma_red": 1.5,
                "gamma_green": 1.2,
                "gamma_blue": 0.7,
                "fade_seconds": 2.5,
            },
        )


if __name__ == "__main__":
    _ = unittest.main()
