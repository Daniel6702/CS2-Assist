from __future__ import annotations

import threading
from contextlib import suppress

from app.components.base import BaseComponent
from app.platform import linux_input


class SnapTap:
    def __init__(self, ui, movement_keys: set[int], axis_of: dict[int, str]) -> None:
        self.ui = ui
        self.movement_keys = movement_keys
        self.axis_of = axis_of
        self.held = {"horizontal": [], "vertical": []}
        self.active = {"horizontal": None, "vertical": None}

    def update_axis(self, axis: str) -> None:
        current = self.active[axis]
        desired = self.held[axis][-1] if self.held[axis] else None
        if current == desired:
            return
        if current is not None:
            linux_input.emit(self.ui, current, 0, syn=False)
        if desired is not None:
            linux_input.emit(self.ui, desired, 1, syn=False)
        self.ui.syn()
        self.active[axis] = desired

    def handle(self, key: int, value: int) -> None:
        if value == 2:
            return
        axis = self.axis_of[key]
        stack = self.held[axis]
        if value == 1:
            if key in stack:
                stack.remove(key)
            stack.append(key)
        elif value == 0:
            if key in stack:
                stack.remove(key)
        self.update_axis(axis)

    def release_all(self) -> None:
        for axis, key in self.active.items():
            if key is not None:
                linux_input.emit(self.ui, key, 0, syn=False)
            self.active[axis] = None
            self.held[axis].clear()
        self.ui.syn()


class SnapTapComponent(BaseComponent):
    name = "snap_tap"

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._active_snap: SnapTap | None = None
        self._state_lock = threading.RLock()

    def on_runtime_gate_changed(self, open_: bool, reason: str) -> None:
        if open_:
            return
        with self._state_lock:
            snap = self._active_snap
        if snap is not None:
            with suppress(Exception):
                snap.release_all()

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
        movement_keys = {c.KEY_W, c.KEY_A, c.KEY_S, c.KEY_D}
        axis_of = {
            c.KEY_W: "vertical",
            c.KEY_S: "vertical",
            c.KEY_A: "horizontal",
            c.KEY_D: "horizontal",
        }
        device_path = str(self._config.get("device_path", ""))

        def on_attach(ui) -> None:
            snap = SnapTap(ui, movement_keys=movement_keys, axis_of=axis_of)
            with self._state_lock:
                self._active_snap = snap

        def on_detach() -> None:
            with self._state_lock:
                snap = self._active_snap
                self._active_snap = None
            if snap is not None:
                with suppress(Exception):
                    snap.release_all()

        def on_event(event, _ui) -> bool:
            if event.type != c.EV_KEY:
                return False
            key = event.code
            with self._state_lock:
                snap = self._active_snap
            if key not in movement_keys:
                return False
            if snap is None:
                return False
            if not self.automation_permitted():
                snap.release_all()
                return False
            snap.handle(key, event.value)
            return True

        runner = linux_input.LinuxKeyboardRunner(
            device_path=device_path,
            required_keys=movement_keys,
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
