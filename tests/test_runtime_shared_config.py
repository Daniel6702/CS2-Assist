from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.optional_dependency_stubs import install_mss_stub, install_pynput_stub

install_mss_stub()
install_pynput_stub()

from app.components.base import BaseComponent
from app.components.long_jump import LongJumpComponent
from app.platform.monitor import MonitorGeometry
from app.runtime import RuntimeManager


class FakeCommandBridge:
    def __init__(self) -> None:
        self.commands: list[tuple[int, str]] = []

    def send(self, slot: int, command: str) -> None:
        self.commands.append((slot, command))


class RuntimeSharedConfigTests(unittest.TestCase):
    def test_runtime_registers_long_jump_component_with_command_bridge(self) -> None:
        bridge = FakeCommandBridge()

        runtime = RuntimeManager(status_callback=lambda _source, _message: None, command_bridge=bridge)

        self.assertIn("long_jump", runtime.components)
        self.assertIsInstance(runtime.components["long_jump"], LongJumpComponent)

    def test_long_jump_receives_shared_keyboard_device(self) -> None:
        runtime = RuntimeManager(status_callback=lambda _source, _message: None, command_bridge=FakeCommandBridge())
        profile = {
            "app": {"shared": {"keyboard_device_path": "/dev/input/event9"}},
            "components": {"long_jump": {"enabled": True, "key_name": "g"}},
        }

        cfg = runtime._effective_component_config(profile, "long_jump")

        self.assertEqual(cfg["device_path"], "/dev/input/event9")
        self.assertEqual(cfg["key_name"], "g")

    def test_restart_component_restarts_enabled_cv_trigger(self) -> None:
        class RestartProbeComponent(BaseComponent):
            name = "cv_trigger"

            def __init__(self) -> None:
                super().__init__()
                self.starts = 0
                self.stops = 0

            def start(self) -> None:
                self.starts += 1
                super().start()

            def stop(self) -> None:
                self.stops += 1
                super().stop()

        runtime = RuntimeManager(status_callback=lambda _source, _message: None)
        probe = RestartProbeComponent()
        probe.start()
        probe.starts = 0
        runtime.components["cv_trigger"] = probe
        profile = {
            "app": {"shared": {"game_sensitivity": 1.0}},
            "components": {
                "cv_trigger": {
                    "enabled": True,
                    "inference_confidence": 0.42,
                },
            },
        }

        with patch("app.runtime.default_monitor_geometry", return_value=MonitorGeometry(left=0, top=0, width=2560, height=1440)):
            runtime.restart_component("cv_trigger", profile)

        self.assertEqual(probe.stops, 1)
        self.assertEqual(probe.starts, 1)
        self.assertTrue(probe.enabled)
        self.assertEqual(probe.config["inference_confidence"], 0.42)

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

    def test_pixel_trigger_uses_shared_resolution_settings(self) -> None:
        runtime = RuntimeManager(status_callback=lambda _source, _message: None)
        profile = {
            "app": {
                "shared": {
                    "game_resolution": {"width": 1600, "height": 1200},
                    "display_resolution": {"width": 2560, "height": 1440},
                    "game_resolution_stretched": False,
                },
            },
            "components": {
                "pixel_trigger": {
                    "game_resolution": {"width": 1024, "height": 768},
                    "display_resolution": {"width": 1920, "height": 1080},
                    "stretched": True,
                },
            },
        }

        cfg = runtime._effective_component_config(profile, "pixel_trigger")

        self.assertEqual(cfg["game_resolution"], {"width": 1600, "height": 1200})
        self.assertEqual(cfg["display_resolution"], {"width": 2560, "height": 1440})
        self.assertFalse(cfg["game_resolution_stretched"])

    def test_runtime_does_not_inject_safety_config(self) -> None:
        runtime = RuntimeManager(status_callback=lambda _source, _message: None)
        profile = {
            "app": {
                "shared": {"game_sensitivity": 1.0},
                "safety": {
                    "enabled": True,
                    "obscure_device_names": False,
                    "recoil": {"jitter_step_fraction": 0.5},
                    "pixel_trigger": {"jitter_poll_fraction": 0.5},
                    "cv_trigger": {"eased_movement_enabled": True},
                },
            },
            "components": {
                "recoil": {},
                "pixel_trigger": {},
                "cv_trigger": {},
            },
        }

        with patch("app.runtime.default_monitor_geometry", return_value=MonitorGeometry(left=0, top=0, width=2560, height=1440)):
            configs = {
                name: runtime._effective_component_config(profile, name)
                for name in ("recoil", "pixel_trigger", "cv_trigger")
            }

        for name, cfg in configs.items():
            with self.subTest(component=name):
                self.assertNotIn("_safety", cfg)


if __name__ == "__main__":
    _ = unittest.main()
