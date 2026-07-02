from __future__ import annotations

import time

try:
    import uinput  # type: ignore
except ImportError:  # pragma: no cover
    uinput = None

from app.utils.input_safety import ORIGINAL_CV_MOUSE_NAME, device_name, eased_movement_steps, humanize_sleep


class VirtualMouse:
    def __init__(self, obscure: bool = False) -> None:
        if uinput is None:
            raise RuntimeError("python-uinput is required for CV trigger on Linux.")
        self._btn_left = uinput.BTN_LEFT
        self._rel_x = uinput.REL_X
        self._rel_y = uinput.REL_Y
        self.ui = uinput.Device(
            [self._btn_left, self._rel_x, self._rel_y],
            name=device_name(ORIGINAL_CV_MOUSE_NAME, obscure=obscure),
        )
        humanize_sleep(0.05, fraction=0.3, min_val=0.02)

    def emit_rel(self, dx: int, dy: int) -> None:
        """Single-frame emit — fast path for small corrections."""
        if dx or dy:
            self.ui.emit(self._rel_x, dx, syn=False)
            self.ui.emit(self._rel_y, dy)

    def eased_emit_rel(self, dx: int, dy: int) -> None:
        """Multi-frame emit with smoothstep easing and micro-sleeps between frames.

        Use this instead of *emit_rel* when the input monitor risk is high
        (e.g. large corrections, first-shot snap) to avoid a single-frame
        teleport signal.
        """
        if dx == 0 and dy == 0:
            return
        steps = eased_movement_steps(dx, dy)
        for i, (sdx, sdy) in enumerate(steps):
            if sdx or sdy:
                self.ui.emit(self._rel_x, sdx, syn=False)
                self.ui.emit(self._rel_y, sdy)
            if i < len(steps) - 1:
                humanize_sleep(0.004, fraction=0.3, min_val=0.001)

    def click_once(self, hold_ms: int) -> None:
        self.ui.emit(self._btn_left, 1)
        time.sleep(max(1, hold_ms) / 1000.0)
        self.ui.emit(self._btn_left, 0)
