from __future__ import annotations

import unittest
from unittest.mock import patch

from app.platform.monitor import MonitorGeometry
from app.runtime import RuntimeManager


class RuntimeSharedConfigTests(unittest.TestCase):
    def test_cv_trigger_uses_shared_game_resolution_and_auto_monitor(self) -> None:
        runtime = RuntimeManager(status_callback=lambda _source, _message: None)
        profile = {
            "app": {
                "shared": {
                    "game_sensitivity": 2.0,
                    "game_resolution": {"width": 1920, "height": 1080},
                },
            },
            "components": {"cv_trigger": {"enabled": True}},
        }

        with patch("app.runtime.default_monitor_geometry", return_value=MonitorGeometry(left=0, top=0, width=3440, height=1440)):
            cfg = runtime._effective_component_config(profile, "cv_trigger")

        self.assertEqual(cfg["user_sens"], 2.0)
        self.assertEqual(cfg["game_resolution"], {"width": 1920, "height": 1080})
        self.assertEqual(cfg["monitor"], {"left": 0, "top": 0, "width": 3440, "height": 1440})

    def test_cv_trigger_falls_back_to_legacy_component_resolution(self) -> None:
        runtime = RuntimeManager(status_callback=lambda _source, _message: None)
        profile = {
            "app": {"shared": {"game_sensitivity": 1.0}},
            "components": {"cv_trigger": {"game_resolution": {"width": 1280, "height": 960}}},
        }

        with patch("app.runtime.default_monitor_geometry", return_value=MonitorGeometry(left=0, top=0, width=2560, height=1440)):
            cfg = runtime._effective_component_config(profile, "cv_trigger")

        self.assertEqual(cfg["game_resolution"], {"width": 1280, "height": 960})


if __name__ == "__main__":
    _ = unittest.main()
