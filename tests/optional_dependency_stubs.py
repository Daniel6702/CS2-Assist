from __future__ import annotations

import sys
import types


def install_mss_stub() -> None:
    if "mss" in sys.modules:
        return
    mss_stub = types.ModuleType("mss")
    mss_stub.mss = object
    sys.modules["mss"] = mss_stub


def install_pynput_stub() -> None:
    if "pynput" in sys.modules:
        return

    pynput_stub = types.ModuleType("pynput")
    mouse_stub = types.ModuleType("pynput.mouse")
    keyboard_stub = types.ModuleType("pynput.keyboard")

    class MouseButton:
        left = "left"
        right = "right"
        middle = "middle"

    class Listener:
        def __init__(self, *args, **kwargs) -> None:
            self.started = False

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.started = False

    class Controller:
        def press(self, button) -> None:
            return

        def release(self, button) -> None:
            return

        def move(self, dx: int, dy: int) -> None:
            return

    class Key:
        alt = "alt"
        alt_l = "alt_l"
        alt_r = "alt_r"
        shift = "shift"
        shift_l = "shift_l"
        shift_r = "shift_r"
        ctrl = "ctrl"
        ctrl_l = "ctrl_l"
        ctrl_r = "ctrl_r"
        space = "space"
        tab = "tab"
        caps_lock = "caps_lock"

    class KeyCode:
        def __init__(self, char: str | None = None) -> None:
            self.char = char

    mouse_stub.Button = MouseButton
    mouse_stub.Listener = Listener
    mouse_stub.Controller = Controller
    keyboard_stub.Key = Key
    keyboard_stub.KeyCode = KeyCode
    keyboard_stub.Listener = Listener
    pynput_stub.mouse = mouse_stub
    pynput_stub.keyboard = keyboard_stub
    sys.modules["pynput"] = pynput_stub
    sys.modules["pynput.mouse"] = mouse_stub
    sys.modules["pynput.keyboard"] = keyboard_stub
