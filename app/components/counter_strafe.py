from __future__ import annotations

import math
import threading
import time
from contextlib import suppress
from dataclasses import dataclass

from app.components.base import BaseComponent
from app.platform import linux_input


@dataclass
class Config:
    base_counter_ms: int = 100
    full_speed_ms: int = 180
    min_counter_ms: int = 8
    max_counter_ms: int = 120
    shift_factor: float = 0.45
    ctrl_factor: float = 0.35
    curve: str = "linear"
    manual_brake_window_ms: int = 150
    manual_brake_max_ms: int = 170
    min_hold_ms: int = 120


class CounterStrafe:
    def __init__(self, ui, cfg: Config, key_constants: dict[str, int]) -> None:
        self.ui = ui
        self.cfg = cfg
        self.c = key_constants
        self.lock = threading.RLock()

        self.stack = {"x": [], "y": []}
        self.active = {"x": None, "y": None}
        self.active_since = {"x": None, "y": None}
        self.counter_tap = {"x": None, "y": None}
        self.counter_timer = {"x": None, "y": None}
        self.last_released_key = {"x": None, "y": None}
        self.last_release_time = {"x": None, "y": None}
        self.manual_brake_key = {"x": None, "y": None}
        self.manual_brake_since = {"x": None, "y": None}

        self.shift_held = False
        self.ctrl_held = False

        # Per-axis flag: suppress the next counter-tap on key release.
        # Set on jump-landing so releasing a direction key that was held
        # through the jump does not fire an unwanted counter-strafe.
        self._suppress_next_release: dict[str, bool] = {"x": False, "y": False}

        self.axis_of = {
            self.c["KEY_W"]: "y",
            self.c["KEY_S"]: "y",
            self.c["KEY_A"]: "x",
            self.c["KEY_D"]: "x",
        }
        self.opposite_of = {
            self.c["KEY_W"]: self.c["KEY_S"],
            self.c["KEY_S"]: self.c["KEY_W"],
            self.c["KEY_A"]: self.c["KEY_D"],
            self.c["KEY_D"]: self.c["KEY_A"],
        }

    def modifier_event(self, key: int, value: int) -> None:
        if value == 2:
            return
        pressed = value == 1
        if key in {self.c["KEY_LSHIFT"], self.c["KEY_RSHIFT"]}:
            self.shift_held = pressed
        elif key in {self.c["KEY_LCTRL"], self.c["KEY_RCTRL"]}:
            self.ctrl_held = pressed

    def modifier_factor(self) -> float:
        if self.shift_held and self.ctrl_held:
            return min(self.cfg.shift_factor, self.cfg.ctrl_factor)
        if self.shift_held:
            return self.cfg.shift_factor
        if self.ctrl_held:
            return self.cfg.ctrl_factor
        return 1.0

    def speed_factor(self, hold_ms: float) -> float:
        hold_ms = max(0.0, hold_ms)
        if self.cfg.curve == "exp":
            tau = self.cfg.full_speed_ms / 3.0
            return max(0.0, min(1.0, 1.0 - math.exp(-hold_ms / tau)))
        return max(0.0, min(1.0, hold_ms / self.cfg.full_speed_ms))

    def counter_duration(self, axis: str) -> int:
        since = self.active_since[axis]
        hold_ms = 0.0 if since is None else (time.perf_counter() - since) * 1000.0
        duration = self.cfg.base_counter_ms
        duration *= self.speed_factor(hold_ms)
        duration *= self.modifier_factor()
        if duration <= 0:
            return 0
        duration = int(round(duration))
        duration = max(self.cfg.min_counter_ms, duration)
        duration = min(self.cfg.max_counter_ms, duration)
        return duration

    def desired_key(self, axis: str) -> int | None:
        return self.stack[axis][-1] if self.stack[axis] else self.counter_tap[axis]

    def apply_axis(self, axis: str) -> None:
        current = self.active[axis]
        desired = self.desired_key(axis)
        if current == desired:
            return
        if current is not None:
            linux_input.emit(self.ui, current, 0, syn=False)
        if desired is not None:
            linux_input.emit(self.ui, desired, 1, syn=False)
            self.active_since[axis] = time.perf_counter()
        else:
            self.active_since[axis] = None
        self.ui.syn()
        self.active[axis] = desired

    def cancel_counter_tap(self, axis: str) -> None:
        timer = self.counter_timer[axis]
        if timer is not None:
            timer.cancel()
        self.counter_timer[axis] = None
        self.counter_tap[axis] = None

    def start_counter_tap(self, axis: str, key: int, duration_ms: int) -> None:
        self.cancel_counter_tap(axis)
        if duration_ms <= 0:
            self.apply_axis(axis)
            return
        self.counter_tap[axis] = key
        self.apply_axis(axis)
        timer = threading.Timer(duration_ms / 1000.0, self.finish_counter_tap, args=(axis, key))
        timer.daemon = True
        self.counter_timer[axis] = timer
        timer.start()

    def finish_counter_tap(self, axis: str, key: int) -> None:
        with self.lock:
            if self.counter_tap[axis] != key:
                return
            self.counter_tap[axis] = None
            self.counter_timer[axis] = None
            self.apply_axis(axis)

    def recent_opposite_release(self, axis: str, key: int, now: float) -> bool:
        last_key = self.last_released_key[axis]
        last_time = self.last_release_time[axis]
        if last_key is None or last_time is None:
            return False
        if key != self.opposite_of[last_key]:
            return False
        elapsed_ms = (now - last_time) * 1000.0
        return elapsed_ms <= self.cfg.manual_brake_window_ms

    def mark_manual_brake(self, axis: str, key: int, now: float) -> None:
        opposite = self.opposite_of[key]
        if self.active[axis] == opposite or self.recent_opposite_release(axis, key, now):
            self.manual_brake_key[axis] = key
            self.manual_brake_since[axis] = now

    def clear_manual_brake(self, axis: str) -> None:
        self.manual_brake_key[axis] = None
        self.manual_brake_since[axis] = None

    def suppress_auto_counter(self, axis: str, key: int, now: float) -> bool:
        if self.manual_brake_key[axis] != key:
            return False
        since = self.manual_brake_since[axis]
        if since is None:
            return False
        hold_ms = (now - since) * 1000.0
        return hold_ms <= self.cfg.manual_brake_max_ms

    def movement_event(self, key: int, value: int) -> None:
        if value == 2:
            return
        with self.lock:
            now = time.perf_counter()
            axis = self.axis_of[key]
            stack = self.stack[axis]
            was_active = self.active[axis] == key

            if value == 1:
                self._suppress_next_release[axis] = False
                self.cancel_counter_tap(axis)
                self.mark_manual_brake(axis, key, now)
                if key in stack:
                    stack.remove(key)
                stack.append(key)
                self.apply_axis(axis)
                return

            if value != 0:
                return

            if key in stack:
                stack.remove(key)

            self.last_released_key[axis] = key
            self.last_release_time[axis] = now

            if stack:
                self.cancel_counter_tap(axis)
                self.apply_axis(axis)
                if self.manual_brake_key[axis] == key:
                    self.clear_manual_brake(axis)
                return

            if self.suppress_auto_counter(axis, key, now):
                self.cancel_counter_tap(axis)
                self.clear_manual_brake(axis)
                self.apply_axis(axis)
                return

            if was_active:
                self.clear_manual_brake(axis)
                if self._suppress_next_release[axis]:
                    self._suppress_next_release[axis] = False
                    self.apply_axis(axis)
                    return
                # Skip counter-tap when the key was held too briefly
                # to build meaningful lateral velocity (e.g. a quick
                # course correction tap while running forward).
                since = self.active_since[axis]
                if since is not None:
                    hold_ms = (now - since) * 1000.0
                    if hold_ms < self.cfg.min_hold_ms:
                        self.apply_axis(axis)
                        return
                self.start_counter_tap(axis, self.opposite_of[key], self.counter_duration(axis))
                return

            self.cancel_counter_tap(axis)
            self.clear_manual_brake(axis)
            self.apply_axis(axis)

    def suppress_post_jump(self) -> None:
        """Suppress counter-tap on the next key release for both axes.

        Called when landing from a jump.  A direction key held through
        the jump should not trigger a counter-strafe when released.
        """
        with self.lock:
            self._suppress_next_release["x"] = True
            self._suppress_next_release["y"] = True

    def release_all(self) -> None:
        with self.lock:
            for axis in ("x", "y"):
                self.cancel_counter_tap(axis)
                self.stack[axis].clear()
                self.clear_manual_brake(axis)
                self._suppress_next_release[axis] = False
                key = self.active[axis]
                if key is not None:
                    linux_input.emit(self.ui, key, 0, syn=False)
                self.active[axis] = None
                self.active_since[axis] = None
                self.last_released_key[axis] = None
                self.last_release_time[axis] = None
            self.ui.syn()

    def suspend(self) -> None:
        """Suspend counter-strafing (e.g. during jump).

        Cancels any running counter-tap timers and releases injected
        keys, but preserves the physical-key tracking stack so state
        stays coherent when normal operation resumes.
        """
        with self.lock:
            for axis in ("x", "y"):
                self.cancel_counter_tap(axis)
                self.clear_manual_brake(axis)
            for axis in ("x", "y"):
                self.apply_axis(axis)

    def track_key(self, key: int, value: int) -> None:
        """Track a movement key during suspend mode without generating a
        counter-tap.

        Updates the tracking stack and emits the key through apply_axis so
        the game sees normal input, but no counter-strafe logic runs.  To
        be called only while *suspend* is active (e.g. jump held).
        """
        if value == 2:
            return
        with self.lock:
            now = time.perf_counter()
            axis = self.axis_of[key]
            stack = self.stack[axis]

            if value == 1:
                if key in stack:
                    stack.remove(key)
                stack.append(key)
                self.apply_axis(axis)
                return

            if value == 0:
                if key in stack:
                    stack.remove(key)
                self.last_released_key[axis] = key
                self.last_release_time[axis] = now
                self.apply_axis(axis)
                return


class CounterStrafeComponent(BaseComponent):
    name = "counter_strafe"

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._active_state: CounterStrafe | None = None
        self._state_lock = threading.RLock()

    def on_runtime_gate_changed(self, open_: bool, reason: str) -> None:
        if open_:
            return
        with self._state_lock:
            state = self._active_state
        if state is not None:
            with suppress(Exception):
                state.release_all()

    def start(self) -> None:
        super().start()
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.status("Started.")

    def stop(self) -> None:
        super().stop()
        self._stop.set()
        self.status("Stopping.")

    def _run(self) -> None:
        if not linux_input.supported():
            self.status("Linux evdev/uinput backend is not available.", "error")
            return

        c = linux_input.ecodes
        key_constants = {
            "KEY_W": c.KEY_W,
            "KEY_A": c.KEY_A,
            "KEY_S": c.KEY_S,
            "KEY_D": c.KEY_D,
            "KEY_SPACE": c.KEY_SPACE,
            "KEY_LSHIFT": c.KEY_LEFTSHIFT,
            "KEY_RSHIFT": c.KEY_RIGHTSHIFT,
            "KEY_LCTRL": c.KEY_LEFTCTRL,
            "KEY_RCTRL": c.KEY_RIGHTCTRL,
        }

        cfg = Config(
            base_counter_ms=int(self._config.get("base_counter_ms", 100)),
            full_speed_ms=int(self._config.get("full_speed_ms", 180)),
            min_counter_ms=int(self._config.get("min_counter_ms", 8)),
            max_counter_ms=int(self._config.get("max_counter_ms", 120)),
            shift_factor=float(self._config.get("shift_factor", 0.45)),
            ctrl_factor=float(self._config.get("ctrl_factor", 0.35)),
            curve=str(self._config.get("curve", "linear")),
            manual_brake_window_ms=int(self._config.get("manual_brake_window_ms", 150)),
            manual_brake_max_ms=int(self._config.get("manual_brake_max_ms", 170)),
            min_hold_ms=int(self._config.get("min_hold_ms", 120)),
        )
        movement_keys = {c.KEY_W, c.KEY_A, c.KEY_S, c.KEY_D}
        modifier_keys = {c.KEY_LEFTSHIFT, c.KEY_RIGHTSHIFT, c.KEY_LEFTCTRL, c.KEY_RIGHTCTRL}
        key_space = c.KEY_SPACE
        required_keys = movement_keys | modifier_keys | {key_space}
        device_path = str(self._config.get("device_path", ""))

        jump_held = [False]

        def on_attach(ui) -> None:
            state = CounterStrafe(ui, cfg, key_constants)
            with self._state_lock:
                self._active_state = state

        def on_detach() -> None:
            with self._state_lock:
                state = self._active_state
                self._active_state = None
            if state is not None:
                with suppress(Exception):
                    state.release_all()

        def on_event(event, _ui) -> bool:
            if event.type != c.EV_KEY:
                return False
            key = event.code
            value = event.value
            with self._state_lock:
                state = self._active_state
            if state is None:
                return False

            if key == key_space and value != 2:
                was_jumping = jump_held[0]
                jump_held[0] = value == 1
                if jump_held[0] and not was_jumping:
                    # Jump pressed — suspend counter-strafing but preserve
                    # the physical-key tracking stack so state stays
                    # coherent when we resume on landing.
                    state.suspend()
                elif not jump_held[0] and was_jumping:
                    # Landed — suppress counter-tap for direction keys
                    # held through the jump so the landing feels natural.
                    state.suppress_post_jump()
                return False

            if not self.automation_permitted():
                state.release_all()
                if key in modifier_keys:
                    state.modifier_event(key, value)
                return False

            if jump_held[0]:
                # While in the air: track keys normally (stack, emission)
                # but never run counter-tap logic.  Modifiers still update
                # so the first counter after landing uses the right factor.
                if key in movement_keys:
                    state.track_key(key, value)
                    return True
                if key in modifier_keys:
                    state.modifier_event(key, value)
                return False

            if key in movement_keys:
                state.movement_event(key, value)
                return True
            if key in modifier_keys:
                state.modifier_event(key, value)
            return False

        runner = linux_input.LinuxKeyboardRunner(
            device_path=device_path,
            required_keys=required_keys,
            component_name=self.name,
            exclusive_keys=movement_keys,
            event_callback=on_event,
            stop_event=self._stop,
            on_attach=on_attach,
            on_detach=on_detach,
            on_error=lambda exc: self.status(str(exc), "error"),
        )
        try:
            runner.run()
        except Exception as exc:
            self.status(str(exc), "error")
        finally:
            self.status("Stopped.")
