from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from app.cs2_integration.cfg_installer import COMMAND_SLOT_COUNT, command_slot_name
from app.platform import linux_input


KEY_F13_CODE: Final[int] = 183
KEY_PRESS: Final[int] = 1
KEY_RELEASE: Final[int] = 0
KEY_TAP_DELAY_SECONDS: Final[float] = 0.001


class KeyEmitter(Protocol):
    def press_release(self, key_code: int) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class InvalidCommandSlotError(Exception):
    slot: int

    def __str__(self) -> str:
        return f"CS2 command slot must be between 1 and {COMMAND_SLOT_COUNT}: {self.slot}"


class UInputKeyEmitter:
    def __init__(self) -> None:
        if not linux_input.supported():
            raise RuntimeError("Linux evdev/uinput backend is not available.")
        keys = list(range(KEY_F13_CODE, KEY_F13_CODE + COMMAND_SLOT_COUNT))
        self._ui = linux_input.UInput(
            {linux_input.ecodes.EV_KEY: keys},
            name="CS2 Assist Command Keyboard",
            bustype=0x03,
            vendor=0x1234,
            product=0x5679,
            version=1,
        )
        time.sleep(0.05)

    def press_release(self, key_code: int) -> None:
        self._ui.write(linux_input.ecodes.EV_KEY, key_code, KEY_PRESS)
        self._ui.syn()
        time.sleep(KEY_TAP_DELAY_SECONDS)
        self._ui.write(linux_input.ecodes.EV_KEY, key_code, KEY_RELEASE)
        self._ui.syn()

    def close(self) -> None:
        self._ui.close()


class CS2CommandBridge:
    def __init__(self, cfg_dir: Path, emitter: KeyEmitter | None = None) -> None:
        self.cfg_dir = cfg_dir
        self._emitter = emitter

    def send(self, slot: int, command: str) -> None:
        if slot < 1 or slot > COMMAND_SLOT_COUNT:
            raise InvalidCommandSlotError(slot=slot)
        slot_path = self.cfg_dir / command_slot_name(slot)
        slot_path.write_text(command)
        self._emitter_for_send().press_release(KEY_F13_CODE + slot - 1)

    def close(self) -> None:
        if self._emitter is not None:
            self._emitter.close()

    def _emitter_for_send(self) -> KeyEmitter:
        if self._emitter is None:
            self._emitter = UInputKeyEmitter()
        return self._emitter
