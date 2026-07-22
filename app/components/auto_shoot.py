from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable, Protocol

from app.components.base import BaseComponent
from app.components.cv_trigger.activation import button_to_name, canonical_weapon_name
from app.components.cv_trigger.virtual_mouse import VirtualMouse
from app.gsi import GameState


class Clicker(Protocol):
    def click_once(self, hold_ms: int) -> None: ...


class MouseListener(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


ListenerFactory = Callable[[Callable[[int, int, Any, bool], None]], MouseListener]


class _PynputClicker:
    def __init__(self) -> None:
        from pynput import mouse

        self._controller = mouse.Controller()
        self._button = mouse.Button.left

    def click_once(self, hold_ms: int) -> None:
        self._controller.press(self._button)
        time.sleep(max(1, hold_ms) / 1000.0)
        self._controller.release(self._button)


def _default_listener_factory(on_click: Callable[[int, int, Any, bool], None]) -> MouseListener:
    from pynput import mouse

    return mouse.Listener(on_click=on_click)


def _default_clicker() -> Clicker:
    try:
        return VirtualMouse()
    except RuntimeError:
        return _PynputClicker()


def _load_allowed_weapons(path_text: str) -> frozenset[str]:
    path = Path(path_text).expanduser()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return frozenset()
    return frozenset(
        canonical_weapon_name(line.strip())
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    )


class AutoShootComponent(BaseComponent):
    name = "auto_shoot"

    def __init__(
        self,
        *,
        clicker: Clicker | None = None,
        listener_factory: ListenerFactory = _default_listener_factory,
    ) -> None:
        super().__init__()
        self._clicker = clicker
        self._listener_factory = listener_factory
        self._listener: MouseListener | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._state_lock = threading.RLock()
        self._mouse1_held = False
        self._current_weapon: str | None = None
        self._allowed_weapons: frozenset[str] = frozenset()
        self._ignore_click_events_until = 0.0
        self._clicks_per_second = 8.0
        self._click_hold_ms = 20

    def configure(self, config: dict[str, Any]) -> None:
        super().configure(config)
        with self._state_lock:
            self._clicks_per_second = max(0.1, float(config.get("clicks_per_second", 8.0) or 8.0))
            self._click_hold_ms = max(1, int(config.get("click_hold_ms", 20) or 20))
            self._allowed_weapons = _load_allowed_weapons(
                str(config.get("allowed_weapon_file", "./resources/weapons_data/semi-auto_weapon_codes.txt") or "./resources/weapons_data/semi-auto_weapon_codes.txt")
            )

    def start(self) -> None:
        if self._thread is not None:
            return
        super().start()
        if self._clicker is None:
            self._clicker = _default_clicker()
        self._stop.clear()
        self._listener = self._listener_factory(self._on_click)
        self._listener.start()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.status("Started. Auto Shoot is active while Mouse1 is held with an allowed GSI weapon.")

    def stop(self) -> None:
        self._stop.set()
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        with self._state_lock:
            self._mouse1_held = False
        super().stop()
        self.status("Stopped.")

    def on_runtime_gate_changed(self, open_: bool, reason: str) -> None:
        if not open_:
            self.set_mouse1_held(False)

    def on_gsi_state(self, state: GameState) -> None:
        with self._state_lock:
            self._current_weapon = canonical_weapon_name(state.current_weapon)

    def set_mouse1_held(self, held: bool) -> None:
        with self._state_lock:
            self._mouse1_held = held

    def _on_click(self, _x: int, _y: int, button: Any, pressed: bool) -> None:
        if button_to_name(button) == "left":
            if not pressed:
                self.set_mouse1_held(False)
                return
            with self._state_lock:
                if time.monotonic() < self._ignore_click_events_until:
                    return
            self.set_mouse1_held(True)

    def _can_click(self) -> bool:
        with self._state_lock:
            return (
                self._mouse1_held
                and self._current_weapon is not None
                and self._current_weapon in self._allowed_weapons
                and self.automation_permitted()
            )

    def _click_settings(self) -> tuple[float, int]:
        with self._state_lock:
            return 1.0 / self._clicks_per_second, self._click_hold_ms

    def _click_once(self, hold_ms: int) -> None:
        with self._state_lock:
            self._ignore_click_events_until = time.monotonic() + (hold_ms / 1000.0) + 0.025
        if self._clicker is not None:
            self._clicker.click_once(hold_ms)

    def _run(self) -> None:
        next_click_at = time.monotonic()
        while not self._stop.is_set():
            interval, hold_ms = self._click_settings()
            now = time.monotonic()
            if not self._can_click():
                next_click_at = now
                time.sleep(0.005)
                continue
            if now < next_click_at:
                time.sleep(min(next_click_at - now, 0.005))
                continue
            self._click_once(hold_ms)
            next_click_at = time.monotonic() + interval
