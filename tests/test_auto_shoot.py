from __future__ import annotations

import os
import sys
import time
import unittest

from tests.optional_dependency_stubs import install_mss_stub, install_pynput_stub

install_mss_stub()
install_pynput_stub()

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6 import QtWidgets  # noqa: E402
except ImportError:
    QtWidgets = None

app = None if QtWidgets is None else QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from app.components.auto_shoot import AutoShootComponent  # noqa: E402
from app.defaults import default_profile  # noqa: E402
from app.gsi import GameState  # noqa: E402
from app.runtime import RuntimeManager  # noqa: E402
if QtWidgets is not None:
    from app.ui.tabs.misc_tab import MiscTab  # noqa: E402


class FakeClicker:
    def __init__(self) -> None:
        self.clicks: list[int] = []

    def click_once(self, hold_ms: int) -> None:
        self.clicks.append(hold_ms)


class FakeMouseListener:
    def __init__(self, on_click) -> None:
        self.on_click = on_click
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


def _state(weapon: str, *, allowed: bool = True) -> GameState:
    return GameState(
        raw={},
        current_weapon=weapon,
        ammo_clip=7,
        ammo_clip_max=7,
        player_alive=allowed,
        round_phase="live",
        map_name="de_dust2",
        features_allowed=allowed,
        kills=0,
        team="T",
        defusekit=False,
        is_scoped=False,
        flashed=False,
    )


def _wait_until(predicate, timeout: float = 0.25) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not reached before timeout")


class AutoShootComponentTests(unittest.TestCase):
    def test_clicks_repeatedly_when_mouse1_held_and_weapon_is_allowed(self) -> None:
        clicker = FakeClicker()
        component = AutoShootComponent(clicker=clicker, listener_factory=FakeMouseListener)
        component.configure(
            {
                "enabled": True,
                "clicks_per_second": 80.0,
                "click_hold_ms": 7,
                "allowed_weapon_file": "./resources/weapons_data/semi-auto_weapon_codes.txt",
            }
        )

        component.start()
        try:
            component.on_gsi_state(_state("weapon_ak47"))
            component.set_mouse1_held(True)
            time.sleep(0.04)
            self.assertEqual(clicker.clicks, [])

            component.on_gsi_state(_state("weapon_deagle"))

            _wait_until(lambda: len(clicker.clicks) >= 2)
        finally:
            component.stop()

        self.assertTrue(all(hold_ms == 7 for hold_ms in clicker.clicks))

    def test_runtime_gate_blocks_clicks_even_for_allowed_weapon(self) -> None:
        clicker = FakeClicker()
        component = AutoShootComponent(clicker=clicker, listener_factory=FakeMouseListener)
        component.configure(
            {
                "enabled": True,
                "clicks_per_second": 80.0,
                "click_hold_ms": 5,
                "allowed_weapon_file": "./resources/weapons_data/semi-auto_weapon_codes.txt",
            }
        )

        component.start()
        try:
            component.set_runtime_gate(False, "player_dead")
            component.on_gsi_state(_state("weapon_deagle", allowed=False))
            component.set_mouse1_held(True)
            time.sleep(0.05)
        finally:
            component.stop()

        self.assertEqual(clicker.clicks, [])

    def test_release_during_generated_click_window_stops_auto_shooting(self) -> None:
        clicker = FakeClicker()
        component = AutoShootComponent(clicker=clicker, listener_factory=FakeMouseListener)
        component.configure(
            {
                "enabled": True,
                "clicks_per_second": 80.0,
                "click_hold_ms": 7,
                "allowed_weapon_file": "./resources/weapons_data/semi-auto_weapon_codes.txt",
            }
        )

        component.start()
        try:
            component.on_gsi_state(_state("weapon_deagle"))
            component._on_click(0, 0, "Button.left", True)
            _wait_until(lambda: len(clicker.clicks) >= 1)

            component._on_click(0, 0, "Button.left", False)
            count_after_release = len(clicker.clicks)
            time.sleep(0.04)

            self.assertEqual(clicker.clicks, clicker.clicks[:count_after_release])
        finally:
            component.stop()


class AutoShootWiringTests(unittest.TestCase):
    def test_runtime_registers_auto_shoot_component(self) -> None:
        runtime = RuntimeManager(status_callback=lambda _source, _message: None)

        self.assertIn("auto_shoot", runtime.components)
        self.assertIsInstance(runtime.components["auto_shoot"], AutoShootComponent)

    def test_default_profile_contains_disabled_auto_shoot_section(self) -> None:
        profile = default_profile()

        self.assertEqual(
            profile["components"]["auto_shoot"],
            {
                "enabled": False,
                "clicks_per_second": 8.0,
                "click_hold_ms": 20,
                "allowed_weapon_file": "./resources/weapons_data/semi-auto_weapon_codes.txt",
            },
        )

    def test_misc_tab_round_trips_auto_shoot_config(self) -> None:
        if QtWidgets is None:
            self.skipTest("PySide6 is unavailable")
        tab = MiscTab()
        try:
            tab.load_config(
                "auto_shoot",
                {
                    "enabled": True,
                    "clicks_per_second": 13.5,
                    "click_hold_ms": 9,
                    "allowed_weapon_file": "./resources/custom_weapons.txt",
                },
            )

            extracted = tab.extract_config()["auto_shoot"]
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()

        self.assertEqual(
            extracted,
            {
                "enabled": True,
                "clicks_per_second": 13.5,
                "click_hold_ms": 9,
                "allowed_weapon_file": "./resources/custom_weapons.txt",
            },
        )


if __name__ == "__main__":
    _ = unittest.main()
