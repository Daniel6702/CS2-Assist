"""Pixel trigger component — single-pixel or multi-point screen monitoring."""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Final, TYPE_CHECKING

from mss import mss
from pynput import keyboard, mouse

from app.components.base import BaseComponent
from app.components.cv_trigger.detection import ScopeDetector
from app.utils.input_safety import humanize_jitter, humanize_sleep

if TYPE_CHECKING:
    import numpy as np


_SCOPE_DETECTION_INTERVAL: Final = 1.0 / 30.0


SPECIAL_KEYS = {
    "shift": keyboard.Key.shift,
    "shift_l": keyboard.Key.shift_l,
    "shift_r": keyboard.Key.shift_r,
    "ctrl": keyboard.Key.ctrl,
    "ctrl_l": keyboard.Key.ctrl_l,
    "ctrl_r": keyboard.Key.ctrl_r,
    "alt": keyboard.Key.alt,
    "alt_l": keyboard.Key.alt_l,
    "alt_r": keyboard.Key.alt_r,
    "space": keyboard.Key.space,
    "caps_lock": keyboard.Key.caps_lock,
    "tab": keyboard.Key.tab,
}


@dataclass
class Config:
    hold_key_name: str
    threshold: float
    click_delay: float
    cooldown: float
    poll_interval: float
    monitor_index: int
    x: int | None  # fallback fixed center X (multi-point mode)
    y: int | None  # fallback fixed center Y (multi-point mode)
    monitor_pixel_x: int | None  # single-pixel X in display-framebuffer coords
    monitor_pixel_y: int | None  # single-pixel Y in display-framebuffer coords
    scope_width: int = 1
    scope_monitor_pixel_x: int | None = None  # scope pixel X in display-framebuffer coords
    scope_monitor_pixel_y: int | None = None  # scope pixel Y in display-framebuffer coords
    scope_blur_offset_x: int = 0
    scope_blur_offset_y: int = 0
    scope_blur_duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class MonitorOrigin:
    left: int
    top: int


@dataclass(frozen=True, slots=True)
class PixelCoordinates:
    x: int
    y: int

    def translated(self, offset_x: int, offset_y: int) -> "PixelCoordinates":
        return PixelCoordinates(x=self.x + offset_x, y=self.y + offset_y)


@dataclass(frozen=True, slots=True)
class ScopeBlurConfig:
    offset_x: int
    offset_y: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class ScopePixelState:
    is_scoped: bool | None
    blur_until: float = 0.0

    def blur_active(self, now: float) -> bool:
        return self.is_scoped is True and now < self.blur_until


@dataclass(frozen=True, slots=True)
class PixelMonitorSelection:
    origin: MonitorOrigin
    base: PixelCoordinates
    scope: PixelCoordinates | None
    blur: ScopeBlurConfig

    def resolve(self, state: ScopePixelState, now: float = 0.0) -> tuple[int, int]:
        selected = self._selected_pixel(state, now)
        return self.origin.left + selected.x, self.origin.top + selected.y

    def _selected_pixel(self, state: ScopePixelState, now: float) -> PixelCoordinates:
        if self.scope is None or state.is_scoped is not True:
            return self.base
        if state.blur_active(now):
            return self.scope.translated(self.blur.offset_x, self.blur.offset_y)
        return self.scope


def update_scope_blur_state(
    previous: ScopePixelState,
    *,
    detected_scoped: bool | None,
    now: float,
    duration_ms: int,
) -> ScopePixelState:
    if detected_scoped is not True:
        return ScopePixelState(is_scoped=detected_scoped, blur_until=0.0)
    if previous.is_scoped is not True and duration_ms > 0:
        return ScopePixelState(is_scoped=True, blur_until=now + (duration_ms / 1000.0))
    return ScopePixelState(is_scoped=True, blur_until=previous.blur_until)


def resolve_pixel_coordinates(
    origin: MonitorOrigin,
    base: PixelCoordinates,
    scope: PixelCoordinates | None,
    is_scoped: bool | None,
) -> tuple[int, int]:
    selection = PixelMonitorSelection(
        origin=origin,
        base=base,
        scope=scope,
        blur=ScopeBlurConfig(offset_x=0, offset_y=0, duration_ms=0),
    )
    return selection.resolve(ScopePixelState(is_scoped=is_scoped))


def parse_hold_key(name: str):
    lower = name.lower()
    if lower in SPECIAL_KEYS:
        return SPECIAL_KEYS[lower]
    if len(name) == 1:
        return keyboard.KeyCode.from_char(name)
    raise ValueError(f"Unsupported key '{name}'.")


def normalize_key(key):
    if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
        return keyboard.Key.shift
    if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
        return keyboard.Key.ctrl
    if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
        return keyboard.Key.alt
    return key


def _safe_stop_listener(listener) -> None:
    if listener is None:
        return
    try:
        listener.stop()
    except Exception:
        return


def color_distance(c1, c2) -> float:
    return math.sqrt(
        (int(c1[0]) - int(c2[0])) ** 2
        + (int(c1[1]) - int(c2[1])) ** 2
        + (int(c1[2]) - int(c2[2])) ** 2
    )


def get_target_center(sct, monitor_index: int, fixed_x: int | None, fixed_y: int | None):
    monitors = sct.monitors
    if monitor_index < 1 or monitor_index >= len(monitors):
        raise ValueError(f"Invalid monitor index: {monitor_index}")
    monitor = monitors[monitor_index]
    if fixed_x is not None and fixed_y is not None:
        center_x = fixed_x
        center_y = fixed_y
    else:
        center_x = monitor["left"] + monitor["width"] // 2
        center_y = monitor["top"] + monitor["height"] // 2
    return center_x, center_y, monitor


def build_monitor_points(center_x: int, center_y: int) -> list[dict[str, int | str]]:
    rect_left = center_x - 2
    rect_right = center_x + 1
    rect_top = center_y - 1
    rect_bottom = center_y
    return [
        {"name": "center", "x": center_x, "y": center_y},
        {"name": "outer_top_left", "x": rect_left - 1, "y": rect_top - 1},
        {"name": "outer_top_right", "x": rect_right + 1, "y": rect_top - 1},
        {"name": "outer_bottom_left", "x": rect_left - 1, "y": rect_bottom + 1},
        {"name": "outer_bottom_right", "x": rect_right + 1, "y": rect_bottom + 1},
    ]


def build_capture_region(points):
    min_x = min(p["x"] for p in points)
    max_x = max(p["x"] for p in points)
    min_y = min(p["y"] for p in points)
    max_y = max(p["y"] for p in points)
    return {"left": min_x, "top": min_y, "width": max_x - min_x + 1, "height": max_y - min_y + 1}


def read_all_pixels(sct, region, points):
    shot = sct.grab(region)
    colors = {}
    for point in points:
        local_x = point["x"] - region["left"]
        local_y = point["y"] - region["top"]
        colors[point["name"]] = shot.pixel(local_x, local_y)
    return colors


def read_single_pixel(sct, abs_x: int, abs_y: int, monitor) -> tuple[int, int, int]:
    """Read a single pixel at absolute monitor coordinates."""
    region = {
        "left": abs_x,
        "top": abs_y,
        "width": 1,
        "height": 1,
    }
    shot = sct.grab(region)
    return shot.pixel(0, 0)


def capture_scope_frame(sct: Any, monitor: dict[str, int]) -> "np.ndarray":
    import cv2
    import numpy as np

    shot = sct.grab(monitor)
    return cv2.cvtColor(np.asarray(shot, np.uint8), cv2.COLOR_BGRA2BGR)


class PixelTriggerComponent(BaseComponent):
    name = "pixel_trigger"

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._scope_pixel_state = ScopePixelState(is_scoped=None)
        self._scope_lock = threading.RLock()

    def scope_state(self) -> bool | None:
        with self._scope_lock:
            return self._scope_pixel_state.is_scoped

    def _pixel_scope_state(self) -> ScopePixelState:
        with self._scope_lock:
            return self._scope_pixel_state

    def _set_scope_state(self, state: ScopePixelState) -> None:
        with self._scope_lock:
            self._scope_pixel_state = state

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
        self._set_scope_state(ScopePixelState(is_scoped=None))
        self.status("Stopping.")

    def _run(self) -> None:
        raw_x = self._config.get("x")
        raw_y = self._config.get("y")
        raw_monitor_px = self._config.get("monitor_pixel_x")
        raw_monitor_py = self._config.get("monitor_pixel_y")
        raw_scope_px = self._config.get("scope_monitor_pixel_x")
        raw_scope_py = self._config.get("scope_monitor_pixel_y")
        raw_scope_blur_x = self._config.get("scope_blur_offset_x")
        raw_scope_blur_y = self._config.get("scope_blur_offset_y")
        raw_scope_blur_ms = self._config.get("scope_blur_duration_ms")
        cfg = Config(
            hold_key_name=str(self._config.get("hold_key_name", "shift")),
            threshold=float(self._config.get("threshold", 35.0)),
            click_delay=float(self._config.get("click_delay", 0.05)),
            cooldown=float(self._config.get("cooldown", 0.15)),
            poll_interval=float(self._config.get("poll_interval", 0.001)),
            monitor_index=int(self._config.get("monitor_index", 1)),
            x=None if raw_x in (None, "") else int(raw_x),
            y=None if raw_y in (None, "") else int(raw_y),
            monitor_pixel_x=None if raw_monitor_px in (None, "") else int(raw_monitor_px),
            monitor_pixel_y=None if raw_monitor_py in (None, "") else int(raw_monitor_py),
            scope_width=int(self._config.get("scope_width", 1)),
            scope_monitor_pixel_x=None if raw_scope_px in (None, "") else int(raw_scope_px),
            scope_monitor_pixel_y=None if raw_scope_py in (None, "") else int(raw_scope_py),
            scope_blur_offset_x=0 if raw_scope_blur_x in (None, "") else int(raw_scope_blur_x),
            scope_blur_offset_y=0 if raw_scope_blur_y in (None, "") else int(raw_scope_blur_y),
            scope_blur_duration_ms=max(0, 0 if raw_scope_blur_ms in (None, "") else int(raw_scope_blur_ms)),
        )

        _sf = dict(self._config.get("_safety", {}))
        _enabled = bool(_sf.get("enabled", False))
        _cooldown_frac = float(_sf.get("jitter_cooldown_fraction", 0.0))
        _click_delay_frac = float(_sf.get("jitter_click_delay_fraction", 0.0))
        _poll_frac = float(_sf.get("jitter_poll_fraction", 0.0))

        held_keys = set()
        mouse_controller = mouse.Controller()

        try:
            hold_key = parse_hold_key(cfg.hold_key_name)
        except ValueError as exc:
            self.status(str(exc), "error")
            return

        def on_press(key):
            normalized = normalize_key(key)
            held_keys.add(normalized)
            held_keys.add(key)

        def on_release(key):
            normalized = normalize_key(key)
            held_keys.discard(key)
            held_keys.discard(normalized)

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()

        use_single_pixel = (
            cfg.monitor_pixel_x is not None and cfg.monitor_pixel_y is not None
        )
        use_scope_pixel = (
            cfg.scope_monitor_pixel_x is not None and cfg.scope_monitor_pixel_y is not None
        )

        try:
            with mss() as sct:
                if use_single_pixel:
                    # ── Single-pixel monitoring mode ──
                    monitors = sct.monitors
                    if cfg.monitor_index < 1 or cfg.monitor_index >= len(monitors):
                        self.status(f"Invalid monitor index: {cfg.monitor_index}", "error")
                        return
                    monitor = monitors[cfg.monitor_index]
                    assert cfg.monitor_pixel_x is not None
                    assert cfg.monitor_pixel_y is not None
                    origin = MonitorOrigin(left=monitor["left"], top=monitor["top"])
                    base_pixel = PixelCoordinates(
                        x=cfg.monitor_pixel_x,
                        y=cfg.monitor_pixel_y,
                    )
                    scope_pixel = None
                    scope_detector = None
                    next_scope_detection_at = 0.0
                    blur = ScopeBlurConfig(
                        offset_x=cfg.scope_blur_offset_x,
                        offset_y=cfg.scope_blur_offset_y,
                        duration_ms=cfg.scope_blur_duration_ms,
                    )
                    if use_scope_pixel:
                        assert cfg.scope_monitor_pixel_x is not None
                        assert cfg.scope_monitor_pixel_y is not None
                        scope_pixel = PixelCoordinates(
                            x=cfg.scope_monitor_pixel_x,
                            y=cfg.scope_monitor_pixel_y,
                        )
                        scope_detector = ScopeDetector()
                        now = time.perf_counter()
                        self._set_scope_state(
                            update_scope_blur_state(
                                self._pixel_scope_state(),
                                detected_scoped=scope_detector.update(capture_scope_frame(sct, monitor)),
                                now=now,
                                duration_ms=cfg.scope_blur_duration_ms,
                            ),
                        )
                        next_scope_detection_at = now + _SCOPE_DETECTION_INTERVAL
                    else:
                        self._set_scope_state(ScopePixelState(is_scoped=None))

                    selection = PixelMonitorSelection(
                        origin=origin,
                        base=base_pixel,
                        scope=scope_pixel,
                        blur=blur,
                    )

                    def _resolve_pixel_coordinates(now: float) -> tuple[int, int]:
                        return selection.resolve(self._pixel_scope_state(), now)

                    prev_abs_x, prev_abs_y = _resolve_pixel_coordinates(time.perf_counter())
                    previous_color = read_single_pixel(sct, prev_abs_x, prev_abs_y, monitor)
                    last_click_time = 0.0
                    pending_click = False
                    pending_click_time = 0.0

                    while not self._stop.is_set():
                        now = time.perf_counter()
                        if scope_detector is not None and now >= next_scope_detection_at:
                            self._set_scope_state(
                                update_scope_blur_state(
                                    self._pixel_scope_state(),
                                    detected_scoped=scope_detector.update(capture_scope_frame(sct, monitor)),
                                    now=now,
                                    duration_ms=cfg.scope_blur_duration_ms,
                                ),
                            )
                            next_scope_detection_at = now + _SCOPE_DETECTION_INTERVAL
                        abs_x, abs_y = _resolve_pixel_coordinates(now)
                        # Reset previous_color when coordinates change (scope <-> unscoped switch)
                        # to prevent a false trigger from the pixel location change itself.
                        if abs_x != prev_abs_x or abs_y != prev_abs_y:
                            prev_abs_x, prev_abs_y = abs_x, abs_y
                            previous_color = read_single_pixel(sct, abs_x, abs_y, monitor)
                            humanize_sleep(cfg.poll_interval, fraction=_poll_frac if _enabled else 0.0, min_val=0.0005)
                            continue
                        current_color = read_single_pixel(sct, abs_x, abs_y, monitor)
                        key_is_held = hold_key in held_keys

                        dist = color_distance(previous_color, current_color)
                        jittered_cooldown = humanize_jitter(
                            cfg.cooldown, fraction=_cooldown_frac if _enabled else 0.0, min_val=0.02,
                        )

                        if not self.automation_permitted() or not key_is_held:
                            pending_click = False
                            previous_color = current_color
                            humanize_sleep(cfg.poll_interval, fraction=_poll_frac if _enabled else 0.0, min_val=0.0005)
                            continue

                        if pending_click:
                            if now >= pending_click_time and now - last_click_time >= jittered_cooldown:
                                mouse_controller.click(mouse.Button.left)
                                last_click_time = now
                                pending_click = False
                                previous_color = current_color
                            humanize_sleep(cfg.poll_interval, fraction=_poll_frac if _enabled else 0.0, min_val=0.0005)
                            continue

                        if now - last_click_time >= jittered_cooldown and dist >= cfg.threshold:
                            pending_click = True
                            pending_click_time = now + humanize_jitter(
                                cfg.click_delay, fraction=_click_delay_frac if _enabled else 0.0, min_val=0.01,
                            )

                        humanize_sleep(cfg.poll_interval, fraction=_poll_frac if _enabled else 0.0, min_val=0.0005)

                else:
                    # ── Legacy multi-point monitoring mode ──
                    center_x, center_y, _monitor = get_target_center(sct, cfg.monitor_index, cfg.x, cfg.y)
                    points = build_monitor_points(center_x, center_y)
                    region = build_capture_region(points)

                    previous_colors = read_all_pixels(sct, region, points)
                    last_click_time = 0.0
                    pending_click = False
                    pending_click_time = 0.0

                    while not self._stop.is_set():
                        now = time.perf_counter()
                        current_colors = read_all_pixels(sct, region, points)
                        key_is_held = hold_key in held_keys

                        distances = {
                            name: color_distance(previous_colors[name], current_colors[name])
                            for name in previous_colors
                        }

                        jittered_cooldown = humanize_jitter(
                            cfg.cooldown, fraction=_cooldown_frac if _enabled else 0.0, min_val=0.02,
                        )

                        if not self.automation_permitted() or not key_is_held:
                            pending_click = False
                            previous_colors = current_colors
                            humanize_sleep(cfg.poll_interval, fraction=_poll_frac if _enabled else 0.0, min_val=0.0005)
                            continue

                        if pending_click:
                            if now >= pending_click_time and now - last_click_time >= jittered_cooldown:
                                mouse_controller.click(mouse.Button.left)
                                last_click_time = now
                                pending_click = False
                                previous_colors = current_colors
                            humanize_sleep(cfg.poll_interval, fraction=_poll_frac if _enabled else 0.0, min_val=0.0005)
                            continue

                        if now - last_click_time >= jittered_cooldown:
                            changed_points = []
                            for point in points:
                                name = point["name"]
                                dist = distances[name]
                                if dist >= cfg.threshold:
                                    changed_points.append({"name": name, "distance": dist})

                            if changed_points:
                                pending_click = True
                                pending_click_time = now + humanize_jitter(
                                    cfg.click_delay, fraction=_click_delay_frac if _enabled else 0.0, min_val=0.01,
                                )

                        humanize_sleep(cfg.poll_interval, fraction=_poll_frac if _enabled else 0.0, min_val=0.0005)
        except Exception as exc:
            self.status(str(exc), "error")
        finally:
            _safe_stop_listener(listener)
            self._set_scope_state(ScopePixelState(is_scoped=None))
            self.status("Stopped.")
