from __future__ import annotations

import random
import threading
import time
from contextlib import suppress
from typing import Callable, Protocol

from app.components.base import BaseComponent
from app.components.jump_throw import evdev_key_code
from app.platform import linux_input


LONG_JUMP_COMMAND_SLOT = 7
_MIN_DELAY_SECONDS = 0.001
_MAX_DELAY_SECONDS = 0.005


class CommandBridge(Protocol):
    def send(self, slot: int, command: str) -> None: ...


class LongJumpAction:
    def __init__(self, bridge: CommandBridge, bind_key: int, sleep: Callable[[float], None] = time.sleep) -> None:
        self.bridge = bridge
        self.bind_key = bind_key
        self._sleep = sleep
        self._active = False
        self._duck_held = False

    def handle(self, key: int, value: int, permitted: bool) -> bool:
        if key != self.bind_key:
            return False
        if value == 2:
            return True
        if not permitted:
            self.release_all()
            return True
        if value == 1:
            self._press()
            return True
        if value == 0:
            self.release_all()
            return True
        return True

    def release_all(self) -> None:
        if not self._duck_held:
            self._active = False
            return
        self.bridge.send(LONG_JUMP_COMMAND_SLOT, "duck -999 1 0")
        self._duck_held = False
        self._active = False

    def _press(self) -> None:
        if self._active:
            return
        self.bridge.send(LONG_JUMP_COMMAND_SLOT, "jump 1 1 0")
        self._sleep(_random_delay_seconds())
        self.bridge.send(LONG_JUMP_COMMAND_SLOT, "duck 1 1 0")
        self._duck_held = True
        self._active = True
        self._sleep(_random_delay_seconds())
        self.bridge.send(LONG_JUMP_COMMAND_SLOT, "jump -999 1 0")


def _random_delay_seconds() -> float:
    return random.randint(1, 5) / 1000.0


class LongJumpComponent(BaseComponent):
    name = "long_jump"

    def __init__(self, command_bridge: CommandBridge | None = None) -> None:
        super().__init__()
        self._command_bridge = command_bridge
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._action: LongJumpAction | None = None
        self._state_lock = threading.RLock()

    def set_command_bridge(self, command_bridge: CommandBridge | None) -> None:
        with self._state_lock:
            action = self._action
            self._action = None
            self._command_bridge = command_bridge
        if action is not None:
            with suppress(RuntimeError, OSError):
                action.release_all()

    def on_runtime_gate_changed(self, open_: bool, reason: str) -> None:
        if open_:
            return
        with self._state_lock:
            action = self._action
        if action is not None:
            with suppress(RuntimeError, OSError):
                action.release_all()

    def start(self) -> None:
        super().start()
        if self._command_bridge is None:
            self.status("CS2 command bridge is not configured.", "error")
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.status("Started.")

    def stop(self) -> None:
        super().stop()
        self._stop.set()
        with self._state_lock:
            action = self._action
        if action is not None:
            with suppress(RuntimeError, OSError):
                action.release_all()
        self.status("Stopping.")

    def _run(self) -> None:
        if self._command_bridge is None:
            self.status("CS2 command bridge is not configured.", "error")
            return
        if not linux_input.supported():
            self.status("Linux evdev/uinput backend is not available.", "error")
            return

        c = linux_input.ecodes
        bind_key = evdev_key_code(str(self._config.get("key_name", "v") or "v"), c)
        device_path = str(self._config.get("device_path", ""))

        def on_attach(_ui) -> None:
            action = LongJumpAction(bridge=self._command_bridge, bind_key=bind_key)
            with self._state_lock:
                self._action = action

        def on_detach() -> None:
            with self._state_lock:
                action = self._action
                self._action = None
            if action is not None:
                with suppress(RuntimeError, OSError):
                    action.release_all()

        def on_event(event, _ui) -> bool:
            if event.type != c.EV_KEY:
                return False
            with self._state_lock:
                action = self._action
            if action is None:
                return False
            return action.handle(event.code, event.value, self.automation_permitted())

        runner = linux_input.LinuxKeyboardRunner(
            device_path=device_path,
            required_keys={bind_key},
            component_name=self.name,
            exclusive_keys={bind_key},
            event_callback=on_event,
            stop_event=self._stop,
            on_attach=on_attach,
            on_detach=on_detach,
            on_error=lambda exc: self.status(str(exc), "error"),
        )
        try:
            runner.run()
        except (RuntimeError, OSError, ValueError) as exc:
            self.status(str(exc), "error")
        finally:
            self.status("Stopped.")
