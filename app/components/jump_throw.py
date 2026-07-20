from __future__ import annotations

import threading
import time
from contextlib import suppress
from typing import Any, Protocol

from app.components.base import BaseComponent
from app.components.cv_trigger.virtual_mouse import VirtualMouse
from app.platform import linux_input


_KEY_ALIASES: dict[str, str] = {
    "ctrl": "KEY_LEFTCTRL",
    "control": "KEY_LEFTCTRL",
    "shift": "KEY_LEFTSHIFT",
    "alt": "KEY_LEFTALT",
    "space": "KEY_SPACE",
    "tab": "KEY_TAB",
    "caps_lock": "KEY_CAPSLOCK",
    "capslock": "KEY_CAPSLOCK",
}


DEFAULT_ATTACK_HOLD_MS = 20


class MouseClicker(Protocol):
    def click_once(self, hold_ms: int) -> None: ...


class _PynputMouseClicker:
    def __init__(self) -> None:
        from pynput import mouse

        self._controller = mouse.Controller()
        self._button = mouse.Button.left

    def click_once(self, hold_ms: int) -> None:
        self._controller.press(self._button)
        time.sleep(max(1, hold_ms) / 1000.0)
        self._controller.release(self._button)


def _default_mouse_clicker() -> MouseClicker:
    try:
        return VirtualMouse()
    except RuntimeError:
        return _PynputMouseClicker()


def evdev_key_code(name: str, ecodes_module: Any) -> int:
    normalized = name.strip().lower()
    if not normalized:
        raise ValueError("Jump Throw key is empty")
    key_name = _KEY_ALIASES.get(normalized)
    if key_name is None and len(normalized) == 1 and normalized.isalnum():
        key_name = f"KEY_{normalized.upper()}"
    if key_name is None and normalized.startswith("f") and normalized[1:].isdigit():
        key_name = f"KEY_{normalized.upper()}"
    if key_name is None and normalized.startswith("key_"):
        key_name = normalized.upper()
    if key_name is None or not hasattr(ecodes_module, key_name):
        raise ValueError(f"Unsupported Jump Throw key '{name}'")
    return int(getattr(ecodes_module, key_name))


class JumpThrowAction:
    def __init__(self, ui: Any, mouse: MouseClicker, bind_key: int, jump_key: int) -> None:
        self.ui = ui
        self.mouse = mouse
        self.bind_key = bind_key
        self.jump_key = jump_key
        self._jump_held = False

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
        if self._jump_held:
            linux_input.emit(self.ui, self.jump_key, 0)
            self._jump_held = False

    def _press(self) -> None:
        if not self._jump_held:
            linux_input.emit(self.ui, self.jump_key, 1)
            self._jump_held = True
        self.mouse.click_once(DEFAULT_ATTACK_HOLD_MS)


class JumpThrowComponent(BaseComponent):
    name = "jump_throw"

    def __init__(self, mouse_clicker: MouseClicker | None = None) -> None:
        super().__init__()
        self._mouse_clicker = mouse_clicker
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._action: JumpThrowAction | None = None
        self._state_lock = threading.RLock()

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
        if self._thread is not None and self._thread.is_alive():
            return
        if self._mouse_clicker is None:
            try:
                self._mouse_clicker = _default_mouse_clicker()
            except (ImportError, RuntimeError) as exc:
                self.status(f"Mouse backend unavailable: {exc}", "error")
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
            with suppress(Exception):
                action.release_all()
        self.status("Stopping.")

    def _run(self) -> None:
        if not linux_input.supported():
            self.status("Linux evdev/uinput backend is not available.", "error")
            return

        c = linux_input.ecodes
        bind_key = evdev_key_code(str(self._config.get("key_name", "v") or "v"), c)
        jump_key = c.KEY_SPACE
        device_path = str(self._config.get("device_path", ""))

        def on_attach(ui) -> None:
            if self._mouse_clicker is None:
                raise RuntimeError("Mouse backend unavailable")
            action = JumpThrowAction(ui, mouse=self._mouse_clicker, bind_key=bind_key, jump_key=jump_key)
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
