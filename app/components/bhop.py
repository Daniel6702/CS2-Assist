from __future__ import annotations

import threading
import time
from contextlib import suppress

from app.components.base import BaseComponent
from app.platform import linux_input


class BhopSpam(threading.Thread):
    def __init__(self, owner: "BhopComponent", ui, key_space: int, tap_interval_ms: int) -> None:
        super().__init__(daemon=True)
        self.owner = owner
        self.ui = ui
        self.key_space = key_space
        self.tap_interval = max(1, tap_interval_ms) / 1000.0
        self.enabled = False
        self.running = True

    def run(self) -> None:
        while self.running:
            if self.enabled and self.owner.automation_permitted() and not self.owner._ctrl_blocked():
                linux_input.emit(self.ui, self.key_space, 1, syn=False)
                linux_input.emit(self.ui, self.key_space, 0)
                time.sleep(self.tap_interval)
            else:
                if not self.owner.automation_permitted():
                    self.enabled = False
                time.sleep(0.01)

    def stop_thread(self) -> None:
        self.running = False
        self.join(timeout=1.0)


class BhopComponent(BaseComponent):
    name = "bhop"

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._spammer: BhopSpam | None = None
        self._state_lock = threading.RLock()
        self._ctrl_lock = threading.RLock()
        self._ctrl_pressed = False
        self._ctrl_unblock_time = 0.0

    def _ctrl_blocked(self) -> bool:
        """Return True while Ctrl is held and for 500 ms after release.
        During this window the spammer suppresses all auto-jumps so the
        player can perform tall-box jumps that need a held Ctrl + Space.
        """
        with self._ctrl_lock:
            if self._ctrl_pressed:
                return True
            return time.perf_counter() < self._ctrl_unblock_time

    def on_runtime_gate_changed(self, open_: bool, reason: str) -> None:
        if open_:
            return
        with self._state_lock:
            if self._spammer is not None:
                self._spammer.enabled = False

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
        key_space = c.KEY_SPACE
        ctrl_keys = {c.KEY_LEFTCTRL, c.KEY_RIGHTCTRL}
        config = dict(self._config)
        device_path = str(config.get("device_path", ""))
        tap_interval_ms = int(config.get("tap_interval_ms", 20))

        def on_attach(ui) -> None:
            spammer = BhopSpam(self, ui, key_space=key_space, tap_interval_ms=tap_interval_ms)
            with self._state_lock:
                self._spammer = spammer
            spammer.start()

        def on_detach() -> None:
            with self._state_lock:
                spammer = self._spammer
                self._spammer = None
            if spammer is not None:
                with suppress(Exception):
                    spammer.stop_thread()

        def on_event(event, _ui) -> bool:
            if event.type != linux_input.ecodes.EV_KEY:
                return False
            code = event.code
            value = event.value

            # Track Ctrl state — never consume the event so the game
            # still receives it normally.
            if code in ctrl_keys and value != 2:
                with self._ctrl_lock:
                    self._ctrl_pressed = value == 1
                    if self._ctrl_pressed:
                        self._ctrl_unblock_time = float("inf")
                    else:
                        self._ctrl_unblock_time = time.perf_counter() + 0.5
                return False

            if code != key_space:
                return False
            with self._state_lock:
                spammer = self._spammer
            if spammer is None:
                return False
            if self._ctrl_blocked():
                if value != 2:
                    spammer.enabled = False
                return False
            if not self.automation_permitted():
                if value != 2:
                    spammer.enabled = False
                return False
            if value != 2:
                spammer.enabled = value == 1
            return True

        runner = linux_input.LinuxKeyboardRunner(
            device_path=device_path,
            required_keys={key_space} | ctrl_keys,
            component_name=self.name,
            exclusive_keys={key_space},
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
