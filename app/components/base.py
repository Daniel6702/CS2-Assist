from __future__ import annotations

import threading
from typing import Any, Callable


StatusCallback = Callable[[str, str], None]


class BaseComponent:
    name = "base"

    def __init__(self) -> None:
        self._enabled = False
        self._config: dict[str, Any] = {}
        self._status_callback: StatusCallback | None = None
        self._lock = threading.RLock()
        self._runtime_gate_open = True
        self._runtime_gate_reason = ""

    def set_status_callback(self, callback: StatusCallback) -> None:
        self._status_callback = callback

    def status(self, message: str, level: str = "info") -> None:
        callback = self._status_callback
        if callback is None:
            return
        try:
            callback(self.name, f"[{level.upper()}] {message}")
        except Exception:
            return

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    def configure(self, config: dict[str, Any]) -> None:
        with self._lock:
            self._config = config

    def start(self) -> None:
        with self._lock:
            self._enabled = True

    def stop(self) -> None:
        with self._lock:
            self._enabled = False

    def restart(self) -> None:
        self.stop()
        self.start()

    def set_runtime_gate(self, open_: bool, reason: str = "") -> None:
        with self._lock:
            changed = self._runtime_gate_open != open_ or self._runtime_gate_reason != reason
            self._runtime_gate_open = open_
            self._runtime_gate_reason = reason
        if changed:
            try:
                self.on_runtime_gate_changed(open_, reason)
            except Exception:
                return

    def runtime_gate_open(self) -> bool:
        with self._lock:
            return self._runtime_gate_open

    def automation_permitted(self) -> bool:
        with self._lock:
            return self._enabled and self._runtime_gate_open

    def runtime_gate_reason(self) -> str:
        with self._lock:
            return self._runtime_gate_reason

    def on_runtime_gate_changed(self, open_: bool, reason: str) -> None:
        return

    def on_gsi_state(self, state: Any) -> None:
        return
