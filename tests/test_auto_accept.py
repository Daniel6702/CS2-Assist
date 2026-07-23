from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.optional_dependency_stubs import install_mss_stub, install_pynput_stub

install_mss_stub()
install_pynput_stub()

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6 import QtWidgets  # noqa: E402
except ImportError:
    QtWidgets = None

app = None if QtWidgets is None else QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from app.components.auto_accept import AutoAcceptComponent  # noqa: E402
from app.defaults import default_profile  # noqa: E402
from app.runtime import RuntimeManager  # noqa: E402

if QtWidgets is not None:
    from app.ui.tabs.misc_tab import MiscTab  # noqa: E402


class FakeAcceptClicker:
    def __init__(self) -> None:
        self.clicks: list[tuple[int, int, int]] = []

    def click_at(self, x: int, y: int, hold_ms: int) -> None:
        self.clicks.append((x, y, hold_ms))


class FakeScreenProbe:
    def __init__(self, color: tuple[int, int, int] = (54, 183, 82)) -> None:
        self.color = color
        self.sampled: list[tuple[int, int]] = []

    def size(self) -> tuple[int, int]:
        return 1920, 1080

    def pixel_at(self, x: int, y: int) -> tuple[int, int, int]:
        self.sampled.append((x, y))
        return self.color


def _wait_until(predicate, timeout: float = 0.5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not reached before timeout")


class AutoAcceptComponentTests(unittest.TestCase):
    def test_clicks_accept_when_match_log_line_arrives_and_button_color_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            console_log = Path(temp_dir) / "console.log"
            console_log.write_text("initial line\n", encoding="utf-8")
            clicker = FakeAcceptClicker()
            screen = FakeScreenProbe()
            component = AutoAcceptComponent(clicker=clicker, screen=screen)
            component.configure(
                {
                    "enabled": True,
                    "console_log_path": str(console_log),
                    "waiting_time_seconds": 0.25,
                    "click_hold_ms": 7,
                    "poll_interval_seconds": 0.02,
                }
            )

            component.start()
            try:
                with console_log.open("a", encoding="utf-8") as handle:
                    handle.write("Server confirmed all players are ready\n")

                _wait_until(lambda: len(clicker.clicks) == 1)
            finally:
                component.stop()

        self.assertEqual(clicker.clicks, [(960, 488, 7)])
        self.assertIn((960, 488), screen.sampled)

    def test_missing_log_path_does_not_click_or_crash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            clicker = FakeAcceptClicker()
            component = AutoAcceptComponent(clicker=clicker, screen=FakeScreenProbe())
            component.configure(
                {
                    "enabled": True,
                    "console_log_path": str(Path(temp_dir) / "missing" / "console.log"),
                    "waiting_time_seconds": 0.05,
                    "poll_interval_seconds": 0.02,
                }
            )

            component.start()
            try:
                time.sleep(0.08)
                self.assertTrue(component.enabled)
            finally:
                component.stop()

        self.assertEqual(clicker.clicks, [])


class AutoAcceptWiringTests(unittest.TestCase):
    def test_runtime_registers_auto_accept_component_and_injects_console_log_path(self) -> None:
        expected_path = Path("/tmp/cs2/game/csgo/console.log")
        runtime = RuntimeManager(
            status_callback=lambda _source, _message: None,
            cs2_log_path_provider=lambda: expected_path,
        )

        profile = default_profile()
        runtime.configure_all(profile)

        self.assertIn("auto_accept", runtime.components)
        self.assertIsInstance(runtime.components["auto_accept"], AutoAcceptComponent)
        self.assertEqual(runtime.components["auto_accept"].config["console_log_path"], str(expected_path))

    def test_default_profile_contains_disabled_auto_accept_section(self) -> None:
        profile = default_profile()

        self.assertEqual(
            profile["components"]["auto_accept"],
            {
                "enabled": False,
                "waiting_time_seconds": 5.0,
                "click_hold_ms": 24,
            },
        )

    def test_misc_tab_round_trips_auto_accept_config(self) -> None:
        if QtWidgets is None:
            self.skipTest("PySide6 is unavailable")
        tab = MiscTab()
        try:
            tab.load_config(
                "auto_accept",
                {
                    "enabled": True,
                    "waiting_time_seconds": 3.5,
                    "click_hold_ms": 11,
                },
            )

            extracted = tab.extract_config()["auto_accept"]
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()

        self.assertEqual(
            extracted,
            {
                "enabled": True,
                "waiting_time_seconds": 3.5,
                "click_hold_ms": 11,
            },
        )


if __name__ == "__main__":
    _ = unittest.main()
