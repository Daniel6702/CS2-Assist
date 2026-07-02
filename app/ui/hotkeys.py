from __future__ import annotations

from typing import Any, Callable

from PySide6 import QtCore


HOTKEY_ACTIONS = ("cv_trigger", "recoil", "pixel_trigger", "movement", "stop_all")


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


class HotkeyBridge(QtCore.QObject):
    activated = QtCore.Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._listener: Any | None = None

    def configure(self, hotkeys: dict[str, str]) -> None:
        self.stop()
        bindings: dict[str, Callable[[], None]] = {}
        for action in HOTKEY_ACTIONS:
            key = normalize_hotkey(str(hotkeys.get(action, "") or ""))
            if key:
                bindings[key] = self._emit_action(action)
        if not bindings:
            return
        from pynput import keyboard

        self._listener = keyboard.GlobalHotKeys(bindings)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is None:
            return
        self._listener.stop()
        self._listener = None

    def _emit_action(self, action: str) -> Callable[[], None]:
        def emit() -> None:
            self.activated.emit(action)

        return emit
