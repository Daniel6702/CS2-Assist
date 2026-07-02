from __future__ import annotations

import threading
from typing import Any

try:
    from pynput import keyboard, mouse
except ImportError:
    keyboard = None
    mouse = None


_SPECIAL_KEYS = {} if keyboard is None else {
    keyboard.Key.alt: "alt",
    keyboard.Key.alt_l: "alt",
    keyboard.Key.alt_r: "alt",
    keyboard.Key.shift: "shift",
    keyboard.Key.shift_l: "shift",
    keyboard.Key.shift_r: "shift",
    keyboard.Key.ctrl: "ctrl",
    keyboard.Key.ctrl_l: "ctrl",
    keyboard.Key.ctrl_r: "ctrl",
    keyboard.Key.space: "space",
    keyboard.Key.tab: "tab",
    keyboard.Key.caps_lock: "caps_lock",
}

_MOUSE_BUTTONS = {} if mouse is None else {
    mouse.Button.left: "left",
    mouse.Button.right: "right",
    mouse.Button.middle: "middle",
}


_WEAPON_ALIASES = {
    "ak": "weaponak47",
    "ak47": "weaponak47",
    "m4a1": "weaponm4a1",
    "m4a4": "weaponm4a1",
    "m4a1s": "weaponm4a1silencer",
    "m4a1silencer": "weaponm4a1silencer",
    "famas": "weaponfamas",
    "galil": "weapongalilar",
    "galilar": "weapongalilar",
    "ump": "weaponump45",
    "ump45": "weaponump45",
    "aug": "weaponaug",
    "sg": "weaponsg556",
    "sg553": "weaponsg556",
    "sg556": "weaponsg556",
    "awp": "weaponawp",
    "ssg08": "weaponssg08",
    "scar20": "weaponscar20",
    "g3sg1": "weapong3sg1",
    "glock": "weaponglock",
    "glock18": "weaponglock",
    "usp": "weaponuspsilencer",
    "usps": "weaponuspsilencer",
    "uspsilencer": "weaponuspsilencer",
    "p250": "weaponp250",
    "deagle": "weapondeagle",
    "deserteagle": "weapondeagle",
}

class ActivationState:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._held_keys: set[str] = set()
        self._held_buttons: set[str] = set()

    def press_key(self, name: str | None) -> None:
        if not name:
            return
        with self._lock:
            self._held_keys.add(name)

    def release_key(self, name: str | None) -> None:
        if not name:
            return
        with self._lock:
            self._held_keys.discard(name)

    def press_button(self, name: str | None) -> None:
        if not name:
            return
        with self._lock:
            self._held_buttons.add(name)

    def release_button(self, name: str | None) -> None:
        if not name:
            return
        with self._lock:
            self._held_buttons.discard(name)

    def is_active(self, activation: dict[str, Any]) -> bool:
        device = str(activation.get("device", "keyboard")).strip().lower()
        mode = str(activation.get("mode", "")).strip().lower()
        if mode == "always" or device in {"always", "none", ""}:
            return True
        with self._lock:
            if device == "mouse":
                button = canonical_button_name(str(activation.get("button", "left")))
                return button in self._held_buttons
            key = canonical_key_name(str(activation.get("key", "alt")))
            return key in self._held_keys

    def button_held(self, name: str) -> bool:
        with self._lock:
            return canonical_button_name(name) in self._held_buttons

    def key_held(self, name: str) -> bool:
        with self._lock:
            return canonical_key_name(name) in self._held_keys


def _canon_text(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def canonical_weapon_name(name: str | None) -> str:
    canon = _canon_text(name)
    return _WEAPON_ALIASES.get(canon, canon)


def canonical_key_name(name: str) -> str:
    value = (name or "").strip().lower()
    aliases = {
        "alt_l": "alt",
        "alt_r": "alt",
        "shift_l": "shift",
        "shift_r": "shift",
        "ctrl_l": "ctrl",
        "ctrl_r": "ctrl",
        "control": "ctrl",
        " ": "space",
    }
    return aliases.get(value, value)


def canonical_button_name(name: str) -> str:
    value = (name or "").strip().lower()
    if value.startswith("mouse_"):
        value = value[6:]
    aliases = {
        "button.left": "left",
        "button.right": "right",
        "button.middle": "middle",
        "button.x1": "x1",
        "button.x2": "x2",
        "back": "x1",
        "forward": "x2",
    }
    return aliases.get(value, value)


def key_to_name(key: Any) -> str | None:
    name = _SPECIAL_KEYS.get(key)
    if name is not None:
        return name
    if keyboard is not None and isinstance(key, keyboard.KeyCode):
        if key.char:
            return key.char.lower()
        return None
    text = str(key)
    if text.startswith("Key."):
        return canonical_key_name(text.split(".", 1)[1])
    return None


def button_to_name(button: Any) -> str | None:
    mapped = _MOUSE_BUTTONS.get(button)
    if mapped is not None:
        return mapped
    text = str(button)
    if text.startswith("Button."):
        return canonical_button_name(text.split(".", 1)[1])
    return None
