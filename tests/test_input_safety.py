from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.platform import linux_input
from app.utils.input_safety import OBSCURED_KEYBOARD_NAME, OBSCURED_MOUSE_NAME, device_name


class InputSafetyTests(unittest.TestCase):
    def test_mouse_device_name_is_always_obscured(self) -> None:
        self.assertEqual(device_name("cs2-specific-device"), OBSCURED_MOUSE_NAME)

    def test_virtual_keyboard_name_is_always_obscured(self) -> None:
        created: dict[str, object] = {}

        class FakeDevice:
            def capabilities(self, *, absinfo: bool = False) -> dict[int, list[int]]:
                return {1: [30]}

        def fake_uinput(events: dict[int, list[int]], **kwargs: object) -> object:
            created["events"] = events
            created.update(kwargs)
            return object()

        with (
            patch.object(linux_input, "ecodes", SimpleNamespace(EV_KEY=1)),
            patch.object(linux_input, "UInput", fake_uinput),
            patch("app.platform.linux_input.time.sleep", lambda _seconds: None),
        ):
            linux_input.create_virtual_keyboard(
                FakeDevice(),
                extra_keys={31},
            )

        self.assertEqual(created["name"], OBSCURED_KEYBOARD_NAME)
        self.assertEqual(created["events"], {1: [30, 31]})


if __name__ == "__main__":
    _ = unittest.main()
