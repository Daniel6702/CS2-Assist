from __future__ import annotations

import unittest

from app.components.long_jump import LONG_JUMP_COMMAND_SLOT, LongJumpAction
from app.components.jump_throw import evdev_key_code


class FakeEcodes:
    KEY_G = 34
    KEY_LEFTSHIFT = 42


class FakeCommandBridge:
    def __init__(self) -> None:
        self.commands: list[tuple[int, str]] = []

    def send(self, slot: int, command: str) -> None:
        self.commands.append((slot, command))


class FakeSleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.delays.append(seconds)


class LongJumpActionTests(unittest.TestCase):
    def test_key_resolver_accepts_existing_jump_throw_aliases(self) -> None:
        self.assertEqual(evdev_key_code("g", FakeEcodes), FakeEcodes.KEY_G)
        self.assertEqual(evdev_key_code("shift", FakeEcodes), FakeEcodes.KEY_LEFTSHIFT)

    def test_press_then_release_sends_erscripts_equivalent_sequence(self) -> None:
        bridge = FakeCommandBridge()
        sleeper = FakeSleeper()
        action = LongJumpAction(bridge=bridge, bind_key=34, sleep=sleeper.sleep)

        self.assertTrue(action.handle(key=34, value=1, permitted=True))
        self.assertTrue(action.handle(key=34, value=0, permitted=True))

        self.assertEqual(
            bridge.commands,
            [
                (LONG_JUMP_COMMAND_SLOT, "jump 1 1 0"),
                (LONG_JUMP_COMMAND_SLOT, "duck 1 1 0"),
                (LONG_JUMP_COMMAND_SLOT, "jump -999 1 0"),
                (LONG_JUMP_COMMAND_SLOT, "duck -999 1 0"),
            ],
        )
        self.assertEqual(len(sleeper.delays), 2)

    def test_repeated_press_does_not_duplicate_sequence_until_release(self) -> None:
        bridge = FakeCommandBridge()
        action = LongJumpAction(bridge=bridge, bind_key=34, sleep=lambda _seconds: None)

        self.assertTrue(action.handle(key=34, value=1, permitted=True))
        self.assertTrue(action.handle(key=34, value=1, permitted=True))

        self.assertEqual(len(bridge.commands), 3)

    def test_non_bind_key_is_ignored(self) -> None:
        bridge = FakeCommandBridge()
        action = LongJumpAction(bridge=bridge, bind_key=34, sleep=lambda _seconds: None)

        self.assertFalse(action.handle(key=35, value=1, permitted=True))

        self.assertEqual(bridge.commands, [])

    def test_runtime_gate_release_sends_duck_release_once(self) -> None:
        bridge = FakeCommandBridge()
        action = LongJumpAction(bridge=bridge, bind_key=34, sleep=lambda _seconds: None)

        self.assertTrue(action.handle(key=34, value=1, permitted=True))
        self.assertTrue(action.handle(key=34, value=1, permitted=False))
        action.release_all()

        self.assertEqual(bridge.commands[-1], (LONG_JUMP_COMMAND_SLOT, "duck -999 1 0"))
        self.assertEqual(bridge.commands.count((LONG_JUMP_COMMAND_SLOT, "duck -999 1 0")), 1)


if __name__ == "__main__":
    _ = unittest.main()
