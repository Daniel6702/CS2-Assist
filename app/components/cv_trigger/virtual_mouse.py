from __future__ import annotations

import time

try:
    import uinput  # type: ignore
except ImportError:  # pragma: no cover
    uinput = None


class VirtualMouse:
    def __init__(self) -> None:
        if uinput is None:
            raise RuntimeError("python-uinput is required for CV trigger on Linux.")
        self._btn_left = uinput.BTN_LEFT
        self._rel_x = uinput.REL_X
        self._rel_y = uinput.REL_Y
        self.ui = uinput.Device(
            [self._btn_left, self._rel_x, self._rel_y],
            name="cs2-unified-cv-trigger-mouse",
        )
        time.sleep(0.05)

    def emit_rel(self, dx: int, dy: int) -> None:
        if dx or dy:
            self.ui.emit(self._rel_x, dx, syn=False)
            self.ui.emit(self._rel_y, dy)

    def click_once(self, hold_ms: int) -> None:
        self.ui.emit(self._btn_left, 1)
        time.sleep(max(1, hold_ms) / 1000.0)
        self.ui.emit(self._btn_left, 0)
