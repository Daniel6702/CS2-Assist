from __future__ import annotations

import unittest
from collections.abc import Callable
from dataclasses import dataclass

import app.components.bhop as bhop_module
from app.components.base import BaseComponent
from app.components.bhop import BhopComponent


class FakeEcodes:
    EV_KEY = 1
    KEY_SPACE = 57
    KEY_LEFTCTRL = 29
    KEY_RIGHTCTRL = 97


class FakeUi:
    pass


@dataclass(frozen=True, slots=True)
class FakeEvent:
    type: int
    code: int
    value: int


class FakeBhopSpam:
    def __init__(self, owner: BhopComponent, ui: FakeUi, key_space: int, tap_interval_ms: int) -> None:
        self.owner = owner
        self.ui = ui
        self.key_space = key_space
        self.tap_interval_ms = tap_interval_ms
        self.enabled = False
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop_thread(self) -> None:
        self.stopped = True


class FakeLinuxKeyboardRunner:
    scenario: Callable[["FakeLinuxKeyboardRunner"], None] | None = None

    def __init__(
        self,
        *,
        device_path: str,
        required_keys: set[int],
        component_name: str,
        exclusive_keys: set[int],
        event_callback: Callable[[FakeEvent, FakeUi], bool],
        stop_event,
        on_attach: Callable[[FakeUi], None] | None = None,
        on_detach: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.device_path = device_path
        self.required_keys = required_keys
        self.component_name = component_name
        self.exclusive_keys = exclusive_keys
        self.event_callback = event_callback
        self.stop_event = stop_event
        self.on_attach = on_attach
        self.on_detach = on_detach
        self.on_error = on_error
        self.ui = FakeUi()

    def run(self) -> None:
        if self.on_attach is not None:
            self.on_attach(self.ui)
        if FakeLinuxKeyboardRunner.scenario is not None:
            FakeLinuxKeyboardRunner.scenario(self)
        if self.on_detach is not None:
            self.on_detach()


class BhopComponentTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeLinuxKeyboardRunner.scenario = None
        self.original_supported = bhop_module.linux_input.supported
        self.original_ecodes = bhop_module.linux_input.ecodes
        self.original_runner = bhop_module.linux_input.LinuxKeyboardRunner
        self.original_spam = bhop_module.BhopSpam
        bhop_module.linux_input.supported = lambda: True
        bhop_module.linux_input.ecodes = FakeEcodes
        bhop_module.linux_input.LinuxKeyboardRunner = FakeLinuxKeyboardRunner
        bhop_module.BhopSpam = FakeBhopSpam

    def tearDown(self) -> None:
        bhop_module.linux_input.supported = self.original_supported
        bhop_module.linux_input.ecodes = self.original_ecodes
        bhop_module.linux_input.LinuxKeyboardRunner = self.original_runner
        bhop_module.BhopSpam = self.original_spam
        FakeLinuxKeyboardRunner.scenario = None

    def test_space_is_consumed_for_automatic_bhop_when_ctrl_is_not_held(self) -> None:
        component = BhopComponent()
        BaseComponent.start(component)
        results: list[bool] = []
        enabled_states: list[bool] = []

        def scenario(runner: FakeLinuxKeyboardRunner) -> None:
            results.append(runner.event_callback(FakeEvent(FakeEcodes.EV_KEY, FakeEcodes.KEY_SPACE, 1), runner.ui))
            enabled_states.append(component._spammer.enabled)
            results.append(runner.event_callback(FakeEvent(FakeEcodes.EV_KEY, FakeEcodes.KEY_SPACE, 0), runner.ui))
            enabled_states.append(component._spammer.enabled)

        FakeLinuxKeyboardRunner.scenario = scenario

        component._run()

        self.assertEqual(results, [True, True])
        self.assertEqual(enabled_states, [True, False])

    def test_ctrl_blocks_only_automatic_bhop_not_physical_space(self) -> None:
        component = BhopComponent()
        BaseComponent.start(component)
        results: list[bool] = []
        enabled_states: list[bool] = []

        def scenario(runner: FakeLinuxKeyboardRunner) -> None:
            results.append(runner.event_callback(FakeEvent(FakeEcodes.EV_KEY, FakeEcodes.KEY_LEFTCTRL, 1), runner.ui))
            results.append(runner.event_callback(FakeEvent(FakeEcodes.EV_KEY, FakeEcodes.KEY_SPACE, 1), runner.ui))
            enabled_states.append(component._spammer.enabled)
            results.append(runner.event_callback(FakeEvent(FakeEcodes.EV_KEY, FakeEcodes.KEY_SPACE, 0), runner.ui))
            enabled_states.append(component._spammer.enabled)

        FakeLinuxKeyboardRunner.scenario = scenario

        component._run()

        self.assertEqual(results, [False, False, False])
        self.assertEqual(enabled_states, [False, False])


if __name__ == "__main__":
    _ = unittest.main()
