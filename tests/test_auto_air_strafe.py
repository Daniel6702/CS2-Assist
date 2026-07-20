from __future__ import annotations

import os
import sys
import threading
import unittest

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

import app.components.auto_air_strafe as air_strafe_module  # noqa: E402
from app.components.auto_air_strafe import AutoAirStrafeAction, AutoAirStrafeComponent, MOVE_STEPS, StrafeSequence, scaled_relative_move  # noqa: E402
from app.defaults import default_profile  # noqa: E402
from app.device_service import DeviceService  # noqa: E402
from app.runtime import RuntimeManager  # noqa: E402
from app.ui.tabs.movement_tab import MovementTab  # noqa: E402


class FakeUi:
    def __init__(self) -> None:
        self.syn_count = 0

    def syn(self) -> None:
        self.syn_count += 1


class FakeMouseMover:
    def __init__(self) -> None:
        self.moves: list[tuple[int, int]] = []

    def move_relative(self, dx: int, dy: int) -> None:
        self.moves.append((dx, dy))


class SleepRecorder:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class AutoAirStrafeActionTests(unittest.TestCase):
    def test_scaled_relative_move_uses_shared_sensitivity_against_ahk_reference(self) -> None:
        self.assertEqual(scaled_relative_move(2.6), 15)
        self.assertEqual(scaled_relative_move(1.3), 30)
        self.assertEqual(scaled_relative_move(5.2), 8)

    def test_action_jumps_then_finishes_strafes_with_mouse_centered_inside_airtime(self) -> None:
        emitted: list[tuple[int, int, bool]] = []
        original_emit = air_strafe_module.linux_input.emit

        def fake_emit(_ui, key: int, value: int, syn: bool = True) -> None:
            emitted.append((key, value, syn))

        air_strafe_module.linux_input.emit = fake_emit
        mouse = FakeMouseMover()
        sleep = SleepRecorder()
        try:
            action = AutoAirStrafeAction(
                ui=FakeUi(),
                mouse=mouse,
                jump_key=57,
                left_key=30,
                right_key=32,
                sleep=sleep,
            )

            action.perform(
                sequence=StrafeSequence(strafe_count=3, relative_move=15, jump_duration_seconds=0.800, start_delay_seconds=0.100),
                stop_event=threading.Event(),
            )
        finally:
            air_strafe_module.linux_input.emit = original_emit

        self.assertEqual(
            emitted,
            [(57, 1, True), (57, 0, True), (32, 1, True), (32, 0, True), (30, 1, True), (30, 0, True), (32, 1, True), (32, 0, True)],
        )
        self.assertEqual(mouse.moves[:MOVE_STEPS], [(15, 0)] * MOVE_STEPS)
        self.assertEqual(mouse.moves[MOVE_STEPS : MOVE_STEPS * 2], [(-15, 0)] * MOVE_STEPS)
        self.assertEqual(mouse.moves[MOVE_STEPS * 2 : MOVE_STEPS * 3], [(15, 0)] * MOVE_STEPS)
        self.assertEqual(mouse.moves[MOVE_STEPS * 3 :], [(-15, 0)] * MOVE_STEPS)
        self.assertEqual(sum(dx for dx, _dy in mouse.moves), 0)
        self.assertEqual(sleep.calls[1], 0.100)
        self.assertAlmostEqual(sum(sleep.calls), 0.800, places=6)


class AutoAirStrafeWiringTests(unittest.TestCase):
    def test_runtime_registers_auto_air_strafe_component(self) -> None:
        runtime = RuntimeManager(status_callback=lambda _source, _message: None)

        self.assertIn("auto_air_strafe", runtime.components)
        self.assertIsInstance(runtime.components["auto_air_strafe"], AutoAirStrafeComponent)

    def test_default_profile_contains_disabled_auto_air_strafe_section(self) -> None:
        profile = default_profile()

        self.assertEqual(
            profile["components"]["auto_air_strafe"],
            {
                "enabled": False,
                "key_name": "space",
                "strafe_count": 8,
                "jump_duration_ms": 800,
                "start_delay_ms": 0,
            },
        )

    def test_component_reads_latest_config_for_each_new_sequence(self) -> None:
        component = AutoAirStrafeComponent()
        component.configure({"strafe_count": 2, "game_sensitivity": 2.6, "jump_duration_ms": 800, "start_delay_ms": 0})

        first = component._sequence_from_config()
        component.configure({"strafe_count": 5, "game_sensitivity": 1.3, "jump_duration_ms": 640, "start_delay_ms": 125})
        second = component._sequence_from_config()

        self.assertEqual(first, StrafeSequence(strafe_count=2, relative_move=15, jump_duration_seconds=0.8, start_delay_seconds=0.0))
        self.assertEqual(second, StrafeSequence(strafe_count=5, relative_move=30, jump_duration_seconds=0.64, start_delay_seconds=0.125))

    def test_movement_tab_round_trips_auto_air_strafe_config(self) -> None:
        tab = MovementTab(DeviceService())
        try:
            tab.load_config(
                {
                    "auto_air_strafe": {
                        "enabled": True,
                        "key_name": "x",
                        "strafe_count": 12,
                        "jump_duration_ms": 720,
                        "start_delay_ms": 90,
                    },
                }
            )

            extracted = tab.extract_config()["auto_air_strafe"]
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()

        self.assertEqual(
            extracted,
            {
                "enabled": True,
                "key_name": "x",
                "strafe_count": 12,
                "jump_duration_ms": 720,
                "start_delay_ms": 90,
            },
        )


if __name__ == "__main__":
    _ = unittest.main()
