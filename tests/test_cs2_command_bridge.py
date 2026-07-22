from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.cs2_integration.command_bridge import CS2CommandBridge, InvalidCommandSlotError


class FakeKeyEmitter:
    def __init__(self) -> None:
        self.events: list[int] = []
        self.closed = False

    def press_release(self, key_code: int) -> None:
        self.events.append(key_code)

    def close(self) -> None:
        self.closed = True


class CommandBridgeTests(unittest.TestCase):
    def test_default_bridge_construction_does_not_open_uinput(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.cs2_integration.command_bridge.UInputKeyEmitter", side_effect=RuntimeError("opened")):
                bridge = CS2CommandBridge(cfg_dir=Path(temp_dir))

            bridge.close()

    def test_send_writes_command_before_emitting_hidden_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg_dir = Path(temp_dir)
            emitter = FakeKeyEmitter()
            bridge = CS2CommandBridge(cfg_dir=cfg_dir, emitter=emitter)

            bridge.send(7, "jump 1 1 0")

            self.assertEqual((cfg_dir / "cs2assist_cmd_07.cfg").read_text(), "jump 1 1 0")
            self.assertEqual(emitter.events, [189])

    def test_send_truncates_previous_slot_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cfg_dir = Path(temp_dir)
            slot = cfg_dir / "cs2assist_cmd_03.cfg"
            slot.write_text("say this old command is longer")
            bridge = CS2CommandBridge(cfg_dir=cfg_dir, emitter=FakeKeyEmitter())

            bridge.send(3, "duck -999 1 0")

            self.assertEqual(slot.read_text(), "duck -999 1 0")

    def test_invalid_slot_raises_without_emitting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            emitter = FakeKeyEmitter()
            bridge = CS2CommandBridge(cfg_dir=Path(temp_dir), emitter=emitter)

            with self.assertRaises(InvalidCommandSlotError):
                bridge.send(13, "status")

            self.assertEqual(emitter.events, [])

    def test_close_closes_injected_emitter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            emitter = FakeKeyEmitter()
            bridge = CS2CommandBridge(cfg_dir=Path(temp_dir), emitter=emitter)

            bridge.close()

        self.assertTrue(emitter.closed)

    def test_fake_dispatch_overhead_stays_below_one_second_for_one_hundred_sends(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge = CS2CommandBridge(cfg_dir=Path(temp_dir), emitter=FakeKeyEmitter())
            start = time.perf_counter()

            for _ in range(100):
                bridge.send(1, "status")

            elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    _ = unittest.main()
