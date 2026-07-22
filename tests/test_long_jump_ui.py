from __future__ import annotations

import os
import sys
import unittest

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from app.defaults import default_profile  # noqa: E402
from app.device_service import DeviceService  # noqa: E402
from app.ui.main_window import _MOVEMENT_COMPONENTS  # noqa: E402
from app.ui.tabs.movement_tab import MovementTab  # noqa: E402


class LongJumpUiTests(unittest.TestCase):
    def test_default_profile_contains_disabled_long_jump_section(self) -> None:
        profile = default_profile()

        self.assertEqual(profile["components"]["long_jump"], {"enabled": False, "key_name": "g"})

    def test_movement_tab_round_trips_long_jump_config(self) -> None:
        tab = MovementTab(DeviceService())
        try:
            tab.load_config({"long_jump": {"enabled": True, "key_name": "h"}})

            extracted = tab.extract_config()["long_jump"]
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()

        self.assertEqual(extracted, {"enabled": True, "key_name": "h"})

    def test_long_jump_participates_in_movement_hotkey_group(self) -> None:
        self.assertIn("long_jump", _MOVEMENT_COMPONENTS)


if __name__ == "__main__":
    _ = unittest.main()
