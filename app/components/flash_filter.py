from __future__ import annotations

import math
import os
import shutil
import threading
import time
from typing import Any

from app.components.base import BaseComponent
from app.gsi import GameState
from app.platform.xrandr import (
    DisplayState,
    XrandrError,
    XrandrRunner,
    detect_output,
    read_display_state,
    run_xrandr,
)

DEFAULT_BRIGHTNESS_FACTOR = 0.50
DEFAULT_GAMMA_RED = 1.42
DEFAULT_GAMMA_GREEN = 1.22
DEFAULT_GAMMA_BLUE = 0.80
DEFAULT_FADE_SECONDS = 1.90
DEFAULT_UPDATE_HZ = 30.0
MIN_STRENGTH_CHANGE = 0.008

class FlashFilter:
    def __init__(
        self,
        output: str,
        brightness_factor: float,
        gamma_multipliers: tuple[float, float, float],
        fade_seconds: float,
        update_hz: float,
        runner: XrandrRunner = run_xrandr,
    ) -> None:
        self._runner = runner
        self.output = output or detect_output(runner)
        self.original = read_display_state(self.output, runner)
        self.target = DisplayState(
            brightness=max(0.05, self.original.brightness * brightness_factor),
            gamma_r=self.original.gamma_r * gamma_multipliers[0],
            gamma_g=self.original.gamma_g * gamma_multipliers[1],
            gamma_b=self.original.gamma_b * gamma_multipliers[2],
        )
        self.fade_seconds = max(0.05, fade_seconds)
        self.update_period = 1.0 / max(1.0, min(60.0, update_hz))
        self._flashed = False
        self._generation = 0
        self._stopped = False
        self._last_strength = 0.0
        self._restored = True
        self._state_lock = threading.Lock()
        self._xrandr_lock = threading.Lock()

    @staticmethod
    def _smoothstep(value: float) -> float:
        value = max(0.0, min(1.0, value))
        return value * value * (3.0 - 2.0 * value)

    @staticmethod
    def _log_lerp(start: float, end: float, amount: float) -> float:
        return math.exp(math.log(start) + (math.log(end) - math.log(start)) * amount)

    def _state_for_strength(self, strength: float) -> DisplayState:
        strength = max(0.0, min(1.0, strength))
        return DisplayState(
            brightness=self.original.brightness + (self.target.brightness - self.original.brightness) * strength,
            gamma_r=self._log_lerp(self.original.gamma_r, self.target.gamma_r, strength),
            gamma_g=self._log_lerp(self.original.gamma_g, self.target.gamma_g, strength),
            gamma_b=self._log_lerp(self.original.gamma_b, self.target.gamma_b, strength),
        )

    def _apply_strength(self, strength: float) -> None:
        strength = max(0.0, min(1.0, strength))
        with self._xrandr_lock:
            endpoint_change = strength in (0.0, 1.0) and strength != self._last_strength
            if not endpoint_change and abs(strength - self._last_strength) < MIN_STRENGTH_CHANGE:
                return
            state = self._state_for_strength(strength)
            self._runner(
                "--output",
                self.output,
                "--gamma",
                f"{state.gamma_r:.4f}:{state.gamma_g:.4f}:{state.gamma_b:.4f}",
                "--brightness",
                f"{state.brightness:.4f}",
            )
            self._last_strength = strength
            self._restored = strength == 0.0

    def _apply_if_current(self, generation: int, expected_flashed: bool, strength: float) -> bool:
        with self._state_lock:
            if self._stopped or self._generation != generation or self._flashed != expected_flashed:
                return False
            self._apply_strength(strength)
            return True

    def set_flashed(self, flashed: bool) -> None:
        with self._state_lock:
            if self._stopped or flashed == self._flashed:
                return
            previous = self._flashed
            self._flashed = flashed
            self._generation += 1
            generation = self._generation
        if flashed:
            self._apply_if_current(generation, True, 1.0)
            return
        if previous:
            threading.Thread(target=self._fade_worker, args=(generation,), name="flash-filter-fade", daemon=True).start()

    def _fade_worker(self, generation: int) -> None:
        started_at = time.monotonic()
        while True:
            progress = min(1.0, (time.monotonic() - started_at) / self.fade_seconds)
            strength = 1.0 - self._smoothstep(progress)
            try:
                current = self._apply_if_current(generation, False, strength)
            except XrandrError:
                return
            if not current or progress >= 1.0:
                return
            time.sleep(self.update_period)

    def restore(self) -> None:
        with self._xrandr_lock:
            if self._restored:
                return
            self._runner(
                "--output",
                self.output,
                "--gamma",
                f"{self.original.gamma_r:.4f}:{self.original.gamma_g:.4f}:{self.original.gamma_b:.4f}",
                "--brightness",
                f"{self.original.brightness:.4f}",
            )
            self._last_strength = 0.0
            self._restored = True

    def shutdown(self) -> None:
        with self._state_lock:
            self._stopped = True
            self._generation += 1
        self.restore()


class FlashFilterComponent(BaseComponent):
    name = "flash_filter"

    def __init__(self, runner: XrandrRunner = run_xrandr) -> None:
        super().__init__()
        self._runner = runner
        self._filter: FlashFilter | None = None

    def start(self) -> None:
        if self.enabled:
            return
        if shutil.which("xrandr") is None:
            self.status("xrandr was not found in PATH.", "error")
            return
        if not os.environ.get("DISPLAY"):
            self.status("DISPLAY is not set; flash filter requires an X11 session.", "error")
            return
        try:
            self._filter = self._build_filter()
        except (OSError, ValueError, XrandrError) as exc:
            self._filter = None
            self.status(f"Failed to start: {exc}", "error")
            return
        super().start()
        self.status(f"Started on {self._filter.output}.")

    def stop(self) -> None:
        flash_filter = self._filter
        self._filter = None
        if flash_filter is not None:
            try:
                flash_filter.shutdown()
            except (OSError, XrandrError) as exc:
                self.status(f"Could not restore display state: {exc}", "error")
        super().stop()
        self.status("Stopped.")

    def on_runtime_gate_changed(self, open_: bool, reason: str) -> None:
        if open_:
            return
        flash_filter = self._filter
        if flash_filter is not None:
            flash_filter.set_flashed(False)

    def on_gsi_state(self, state: GameState) -> None:
        flash_filter = self._filter
        if flash_filter is None or state.flashed is None:
            return
        try:
            flash_filter.set_flashed(state.flashed)
        except (OSError, XrandrError) as exc:
            self.status(f"XRandR update failed: {exc}", "error")

    def _build_filter(self) -> FlashFilter:
        cfg = self.config
        brightness_factor = max(0.05, min(1.0, float(cfg.get("brightness_factor", DEFAULT_BRIGHTNESS_FACTOR) or DEFAULT_BRIGHTNESS_FACTOR)))
        gamma = (
            max(0.05, min(5.0, float(cfg.get("gamma_red", DEFAULT_GAMMA_RED) or DEFAULT_GAMMA_RED))),
            max(0.05, min(5.0, float(cfg.get("gamma_green", DEFAULT_GAMMA_GREEN) or DEFAULT_GAMMA_GREEN))),
            max(0.05, min(5.0, float(cfg.get("gamma_blue", DEFAULT_GAMMA_BLUE) or DEFAULT_GAMMA_BLUE))),
        )
        fade_seconds = max(0.05, float(cfg.get("fade_seconds", DEFAULT_FADE_SECONDS) or DEFAULT_FADE_SECONDS))
        update_hz = max(1.0, min(60.0, float(cfg.get("update_hz", DEFAULT_UPDATE_HZ) or DEFAULT_UPDATE_HZ)))
        return FlashFilter(
            output=str(cfg.get("output", "") or ""),
            brightness_factor=brightness_factor,
            gamma_multipliers=gamma,
            fade_seconds=fade_seconds,
            update_hz=update_hz,
            runner=self._runner,
        )
