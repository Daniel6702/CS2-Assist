from __future__ import annotations

import os
import sys
import unittest

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from app.components.jump_throw import JumpThrowAction, JumpThrowComponent, evdev_key_code  # noqa: E402
from app.defaults import default_profile  # noqa: E402
from app.runtime import RuntimeManager  # noqa: E402
from app.ui.tabs.movement_tab import MovementTab  # noqa: E402
from app.device_service import DeviceService  # noqa: E402
import app.components.jump_throw as jump_throw_module  # noqa: E402


class FakeEcodes:
    KEY_V = 47
    KEY_F5 = 63
    KEY_LEFTSHIFT = 42


class FakeMouseClicker:
    def __init__(self) -> None:
        self.clicks: list[int] = []

    def click_once(self, hold_ms: int) -> None:
        self.clicks.append(hold_ms)


class JumpThrowActionTests(unittest.TestCase):
    def test_key_name_resolver_accepts_letters_function_keys_and_aliases(self) -> None:
        self.assertEqual(evdev_key_code("v", FakeEcodes), FakeEcodes.KEY_V)
        self.assertEqual(evdev_key_code("F5", FakeEcodes), FakeEcodes.KEY_F5)
        self.assertEqual(evdev_key_code("shift", FakeEcodes), FakeEcodes.KEY_LEFTSHIFT)

    def test_press_releases_attack_and_holds_jump_until_bind_release(self) -> None:
        emitted: list[tuple[int, int, bool]] = []
        original_emit = jump_throw_module.linux_input.emit

        def fake_emit(_ui, key: int, value: int, syn: bool = True) -> None:
            emitted.append((key, value, syn))

        jump_throw_module.linux_input.emit = fake_emit
        mouse = FakeMouseClicker()
        try:
            action = JumpThrowAction(ui=object(), mouse=mouse, bind_key=47, jump_key=57)

            self.assertTrue(action.handle(47, 1, True))
            self.assertTrue(action.handle(47, 0, True))
        finally:
            jump_throw_module.linux_input.emit = original_emit

        self.assertEqual(emitted, [(57, 1, True), (57, 0, True)])
        self.assertEqual(mouse.clicks, [20])

    def test_runtime_gate_releases_held_jump(self) -> None:
        emitted: list[tuple[int, int, bool]] = []
        original_emit = jump_throw_module.linux_input.emit

        def fake_emit(_ui, key: int, value: int, syn: bool = True) -> None:
            emitted.append((key, value, syn))

        jump_throw_module.linux_input.emit = fake_emit
        mouse = FakeMouseClicker()
        try:
            action = JumpThrowAction(ui=object(), mouse=mouse, bind_key=47, jump_key=57)
            self.assertTrue(action.handle(47, 1, True))
            self.assertTrue(action.handle(47, 1, False))
        finally:
            jump_throw_module.linux_input.emit = original_emit

        self.assertEqual(emitted, [(57, 1, True), (57, 0, True)])
        self.assertEqual(mouse.clicks, [20])


class JumpThrowWiringTests(unittest.TestCase):
    def test_runtime_registers_jump_throw_component(self) -> None:
        runtime = RuntimeManager(status_callback=lambda _source, _message: None)

        self.assertIn("jump_throw", runtime.components)
        self.assertIsInstance(runtime.components["jump_throw"], JumpThrowComponent)

    def test_default_profile_contains_disabled_jump_throw_section(self) -> None:
        profile = default_profile()

        self.assertEqual(profile["components"]["jump_throw"], {"enabled": False, "key_name": "v"})

    def test_movement_tab_round_trips_jump_throw_config(self) -> None:
        tab = MovementTab(DeviceService())
        try:
            tab.load_config({"jump_throw": {"enabled": True, "key_name": "g"}})

            extracted = tab.extract_config()["jump_throw"]
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()

        self.assertEqual(extracted, {"enabled": True, "key_name": "g"})


if __name__ == "__main__":
    _ = unittest.main()
