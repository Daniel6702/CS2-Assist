from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6 import QtCore

_log = logging.getLogger(__name__)

HOTKEY_ACTIONS = ("cv_trigger", "recoil", "pixel_trigger", "movement", "stop_all", "overlay")

_MODIFIER_MAP: dict[str, str] = {
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "alt_l": "alt",
    "alt_r": "alt",
    "shift_l": "shift",
    "shift_r": "shift",
    "cmd_l": "cmd",
    "cmd_r": "cmd",
}


def normalize_hotkey(value: str) -> str:
    parts = [part.strip().lower() for part in value.replace("<", "").replace(">", "").split("+") if part.strip()]
    if not parts:
        return ""
    normalized: list[str] = []
    for part in parts:
        if len(part) == 1:
            normalized.append(part)
        else:
            normalized.append(f"<{part}>")
    return "+".join(normalized)


def _pynput_key_str(key: Any) -> str | None:
    """Convert a pynput key object to our normalized string format.

    Returns ``None`` when the key cannot be represented (unknown key).
    """
    try:
        if hasattr(key, "char") and key.char is not None:
            return key.char.lower()
        if hasattr(key, "name") and key.name:
            name = key.name.lower()
            mapped = _MODIFIER_MAP.get(name, name)
            return f"<{mapped}>"
    except Exception:
        pass
    return None


class _FallbackHotkeyListener:
    """Manual hotkey detector built on ``pynput.keyboard.Listener``.

    ``pynput.keyboard.GlobalHotKeys`` depends on the X record extension
    which is unavailable or broken on many Linux configurations.  This
    class uses the lower-level ``Listener`` (evdev / X input extension)
    instead, which is far more reliable.

    A hotkey combination will only fire once per press-release cycle of
    *all* keys involved (standard hotkey behaviour).
    """

    def __init__(self, bindings: dict[str, Callable[[], None]]) -> None:
        self._bindings = bindings
        self._pressed: set[str] = set()
        self._listener: Any = None
        self._consumed: set[frozenset[str]] = set()
        # Pre-compute every binding as a frozenset of individual key strings.
        self._combo_map: list[tuple[frozenset[str], Callable[[], None]]] = []
        for key_str, callback in bindings.items():
            parts = key_str.split("+")
            keys = frozenset(p.strip().lower() for p in parts if p.strip())
            self._combo_map.append((keys, callback))

    def start(self) -> None:
        from pynput import keyboard

        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._pressed.clear()
        self._consumed.clear()

    def _on_press(self, key: Any) -> None:
        ks = _pynput_key_str(key)
        if ks:
            self._pressed.add(ks)
            self._check_hotkeys()

    def _on_release(self, key: Any) -> None:
        ks = _pynput_key_str(key)
        if ks:
            self._pressed.discard(ks)
        if not self._pressed:
            self._consumed.clear()

    def _check_hotkeys(self) -> None:
        current = frozenset(self._pressed)
        for combo_keys, callback in self._combo_map:
            if combo_keys.issubset(current) and combo_keys not in self._consumed:
                self._consumed.add(combo_keys)
                callback()
                return


class HotkeyBridge(QtCore.QObject):
    activated = QtCore.Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._listener: Any | None = None
        self._mode: str = "none"

    def configure(self, hotkeys: dict[str, str]) -> None:
        self.stop()
        bindings: dict[str, Callable[[], None]] = {}
        for action in HOTKEY_ACTIONS:
            key = normalize_hotkey(str(hotkeys.get(action, "") or ""))
            if key:
                bindings[key] = self._emit_action(action)
        if not bindings:
            self._mode = "none"
            return

        from pynput import keyboard

        # Try GlobalHotKeys first (uses X record extension, fast).
        # Fall back to manual Listener-based detection when it fails.
        try:
            self._listener = keyboard.GlobalHotKeys(bindings)
            self._listener.start()
            self._mode = "global"
        except Exception as exc:
            _log.warning("GlobalHotKeys failed (%s); falling back to manual Listener.", exc)
            try:
                self._listener = _FallbackHotkeyListener(bindings)
                self._listener.start()
                self._mode = "fallback"
            except Exception as fallback_exc:
                _log.error("Fallback hotkey listener also failed: %s", fallback_exc)
                self._listener = None
                self._mode = "error"

    @property
    def mode(self) -> str:
        return self._mode

    def stop(self) -> None:
        if self._listener is None:
            return
        self._listener.stop()
        self._listener = None
        self._mode = "none"

    def _emit_action(self, action: str) -> Callable[[], None]:
        def emit() -> None:
            self.activated.emit(action)

        return emit
