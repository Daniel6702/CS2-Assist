from __future__ import annotations

import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from app.components.base import BaseComponent
from app.components.cv_trigger.virtual_mouse import VirtualMouse
from app.components.jump_throw import evdev_key_code
from app.platform import linux_input

REFERENCE_SENSITIVITY = 2.6
REFERENCE_RELATIVE_MOVE = 15
MOVE_STEPS = 25
KEY_SETTLE_SECONDS = 0.005
JUMP_HOLD_SECONDS = 0.015

SleepFn = Callable[[float], None]


@dataclass(frozen=True, slots=True)
class StrafeSequence:
    strafe_count: int
    relative_move: int
    jump_duration_seconds: float
    start_delay_seconds: float


def _mouse_step_seconds(sequence: StrafeSequence) -> float:
    recenter_steps = MOVE_STEPS if sequence.strafe_count % 2 == 1 else 0
    movement_steps = (sequence.strafe_count * MOVE_STEPS) + recenter_steps
    if movement_steps <= 0:
        return 0.0
    reserved_seconds = JUMP_HOLD_SECONDS + sequence.start_delay_seconds + (sequence.strafe_count * KEY_SETTLE_SECONDS)
    return max(0.0, (sequence.jump_duration_seconds - reserved_seconds) / movement_steps)


class MouseMover(Protocol):
    def move_relative(self, dx: int, dy: int) -> None: ...


class _VirtualMouseMover:
    def __init__(self) -> None:
        self._mouse = VirtualMouse()

    def move_relative(self, dx: int, dy: int) -> None:
        self._mouse.emit_rel(dx, dy)


class _PynputMouseMover:
    def __init__(self) -> None:
        from pynput import mouse

        self._controller = mouse.Controller()

    def move_relative(self, dx: int, dy: int) -> None:
        self._controller.move(dx, dy)


def _default_mouse_mover() -> MouseMover:
    try:
        return _VirtualMouseMover()
    except RuntimeError:
        return _PynputMouseMover()


def scaled_relative_move(game_sensitivity: float) -> int:
    sensitivity = max(0.01, game_sensitivity)
    return max(1, int(round(REFERENCE_RELATIVE_MOVE * REFERENCE_SENSITIVITY / sensitivity)))


class AutoAirStrafeAction:
    def __init__(
        self,
        ui: Any,
        mouse: MouseMover,
        jump_key: int,
        left_key: int,
        right_key: int,
        sleep: SleepFn = time.sleep,
    ) -> None:
        self.ui = ui
        self.mouse = mouse
        self.jump_key = jump_key
        self.left_key = left_key
        self.right_key = right_key
        self._sleep = sleep
        self._held_keys: set[int] = set()

    def perform(
        self,
        sequence: StrafeSequence,
        stop_event: threading.Event,
    ) -> None:
        mouse_step_seconds = _mouse_step_seconds(sequence)
        offset_x = 0
        self._tap_jump()
        if sequence.start_delay_seconds > 0 and not stop_event.is_set():
            self._sleep(sequence.start_delay_seconds)
        for index in range(max(0, sequence.strafe_count)):
            if stop_event.is_set():
                break
            offset_x += self._strafe(
                left=index % 2 == 1,
                sequence=sequence,
                stop_event=stop_event,
            )
        if offset_x != 0 and not stop_event.is_set():
            self._center_mouse(offset_x, mouse_step_seconds, stop_event)
        self.release_all()

    def release_all(self) -> None:
        for key in tuple(self._held_keys):
            linux_input.emit(self.ui, key, 0, syn=False)
            self._held_keys.discard(key)
        self.ui.syn()

    def _tap_jump(self) -> None:
        self._press_key(self.jump_key)
        self._sleep(JUMP_HOLD_SECONDS)
        self._release_key(self.jump_key)

    def _strafe(
        self,
        left: bool,
        sequence: StrafeSequence,
        stop_event: threading.Event,
    ) -> int:
        key = self.left_key if left else self.right_key
        move = -sequence.relative_move if left else sequence.relative_move
        mouse_step_seconds = _mouse_step_seconds(sequence)
        offset_x = 0
        self._press_key(key)
        self._sleep(KEY_SETTLE_SECONDS)
        for _ in range(MOVE_STEPS):
            if stop_event.is_set():
                break
            self.mouse.move_relative(move, 0)
            offset_x += move
            self._sleep(mouse_step_seconds)
        self._release_key(key)
        return offset_x

    def _center_mouse(self, offset_x: int, mouse_step_seconds: float, stop_event: threading.Event) -> None:
        move = -offset_x // MOVE_STEPS
        for _ in range(MOVE_STEPS):
            if stop_event.is_set():
                break
            self.mouse.move_relative(move, 0)
            self._sleep(mouse_step_seconds)

    def _press_key(self, key: int) -> None:
        if key in self._held_keys:
            return
        linux_input.emit(self.ui, key, 1)
        self._held_keys.add(key)

    def _release_key(self, key: int) -> None:
        if key not in self._held_keys:
            return
        linux_input.emit(self.ui, key, 0)
        self._held_keys.discard(key)


class AutoAirStrafeComponent(BaseComponent):
    name = "auto_air_strafe"

    def __init__(self, mouse_mover: MouseMover | None = None) -> None:
        super().__init__()
        self._mouse_mover = mouse_mover
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._sequence_stop = threading.Event()
        self._sequence_thread: threading.Thread | None = None
        self._action: AutoAirStrafeAction | None = None
        self._state_lock = threading.RLock()

    def start(self) -> None:
        super().start()
        if self._thread is not None and self._thread.is_alive():
            return
        if self._mouse_mover is None:
            try:
                self._mouse_mover = _default_mouse_mover()
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
        self._sequence_stop.set()
        self._release_action()
        self.status("Stopping.")

    def on_runtime_gate_changed(self, open_: bool, reason: str) -> None:
        if open_:
            return
        self._sequence_stop.set()
        self._release_action()

    def _release_action(self) -> None:
        with self._state_lock:
            action = self._action
        if action is not None:
            with suppress(RuntimeError, OSError):
                action.release_all()

    def _run(self) -> None:
        if not linux_input.supported():
            self.status("Linux evdev/uinput backend is not available.", "error")
            return
        c = linux_input.ecodes
        bind_key = evdev_key_code(str(self._config.get("key_name", "space") or "space"), c)
        device_path = str(self._config.get("device_path", ""))

        def on_attach(ui) -> None:
            if self._mouse_mover is None:
                raise RuntimeError("Mouse backend unavailable")
            action = AutoAirStrafeAction(
                ui=ui,
                mouse=self._mouse_mover,
                jump_key=c.KEY_SPACE,
                left_key=c.KEY_A,
                right_key=c.KEY_D,
            )
            with self._state_lock:
                self._action = action

        def on_detach() -> None:
            self._sequence_stop.set()
            with self._state_lock:
                action = self._action
                self._action = None
            if action is not None:
                with suppress(RuntimeError, OSError):
                    action.release_all()

        def on_event(event, _ui) -> bool:
            if event.type != c.EV_KEY or event.code != bind_key:
                return False
            if event.value == 1:
                self._start_sequence(self._sequence_from_config())
            return True

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

    def _sequence_from_config(self) -> StrafeSequence:
        with self._lock:
            config = dict(self._config)
        strafe_count = max(1, min(100, int(config.get("strafe_count", 8) or 8)))
        game_sensitivity = float(config.get("game_sensitivity", REFERENCE_SENSITIVITY) or REFERENCE_SENSITIVITY)
        jump_duration_seconds = max(0.100, min(2.000, float(config.get("jump_duration_ms", 800) or 800) / 1000.0))
        start_delay_seconds = max(0.0, min(1.000, float(config.get("start_delay_ms", 0) or 0) / 1000.0))
        return StrafeSequence(strafe_count, scaled_relative_move(game_sensitivity), jump_duration_seconds, start_delay_seconds)

    def _start_sequence(self, sequence: StrafeSequence) -> None:
        if not self.automation_permitted():
            self._release_action()
            return
        with self._state_lock:
            action = self._action
            running = self._sequence_thread is not None and self._sequence_thread.is_alive()
        if action is None or running:
            return
        self._sequence_stop.clear()
        self._sequence_thread = threading.Thread(
            target=action.perform,
            args=(sequence, self._sequence_stop),
            daemon=True,
        )
        self._sequence_thread.start()
