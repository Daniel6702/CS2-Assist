from __future__ import annotations

import os
import sys
import unittest

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from app.device_service import DeviceService  # noqa: E402
from app.ui.tabs.shared_settings_tab import SharedSettingsTab  # noqa: E402


class SharedSettingsTabTests(unittest.TestCase):
    def test_game_resolution_round_trips_from_shared_settings(self) -> None:
        tab = SharedSettingsTab(DeviceService())
        tab.load_config(
            {
                "shared": {
                    "game_resolution": {"width": 1920, "height": 1080},
                    "game_resolution_stretched": False,
                },
            },
        )

        extracted = tab.extract_config()

        self.assertEqual(extracted["shared"]["game_resolution"], {"width": 1920, "height": 1080})
        self.assertFalse(extracted["shared"]["game_resolution_stretched"])

    def test_missing_game_resolution_uses_default(self) -> None:
        tab = SharedSettingsTab(DeviceService())
        tab.load_config({"shared": {}})

        extracted = tab.extract_config()

        self.assertEqual(extracted["shared"]["game_resolution"], {"width": 1600, "height": 1200})
        self.assertTrue(extracted["shared"]["game_resolution_stretched"])

    def test_safety_settings_are_not_exposed_or_extracted(self) -> None:
        tab = SharedSettingsTab(DeviceService())
        tab.load_config(
            {
                "safety": {
                    "enabled": True,
                    "obscure_device_names": False,
                    "pixel_trigger": {"jitter_poll_fraction": 0.5},
                },
            },
        )

        extracted = tab.extract_config()

        self.assertFalse(hasattr(tab, "safety_enabled"))
        self.assertNotIn("safety", extracted)

    def test_change_game_directory_button_emits_request(self) -> None:
        tab = SharedSettingsTab(DeviceService())
        calls: list[bool] = []
        tab.change_game_directory_requested.connect(lambda: calls.append(True))

        tab.change_game_directory_btn.click()

        self.assertEqual(calls, [True])

    def test_gsi_enable_toggle_is_not_exposed_or_extracted(self) -> None:
        tab = SharedSettingsTab(DeviceService())
        tab.load_config({"gsi": {"enabled": False, "host": "0.0.0.0", "port": 4123}})

        extracted = tab.extract_config()

        self.assertFalse(hasattr(tab, "gsi_enabled"))
        self.assertEqual(extracted["gsi"], {"host": "0.0.0.0", "port": 4123})

    def test_gsi_status_indicators_update_text(self) -> None:
        tab = SharedSettingsTab(DeviceService())

        tab.set_gsi_connection_status(True)
        tab.set_gsi_system_active(True)

        self.assertEqual(tab.gsi_connection_status.text(), "Connected")
        self.assertEqual(tab.gsi_system_status.text(), "Active")
        self.assertIn("#4ade80", tab.gsi_system_status.styleSheet())

        tab.set_gsi_system_active(False)

        self.assertEqual(tab.gsi_system_status.text(), "Inactive")
        self.assertIn("#ef4444", tab.gsi_system_status.styleSheet())


if __name__ == "__main__":
    _ = unittest.main()
