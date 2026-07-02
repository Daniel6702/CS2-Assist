from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any

from mss import mss
from pynput import keyboard, mouse

from app.components.base import BaseComponent
from app.utils.input_safety import humanize_jitter, humanize_sleep


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
    x: int | None
    y: int | None


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


class PixelTriggerComponent(BaseComponent):
    name = "pixel_trigger"

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

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
        self.status("Stopping.")

    def _run(self) -> None:
        raw_x = self._config.get("x")
        raw_y = self._config.get("y")
        cfg = Config(
            hold_key_name=str(self._config.get("hold_key_name", "shift")),
            threshold=float(self._config.get("threshold", 35.0)),
            click_delay=float(self._config.get("click_delay", 0.05)),
            cooldown=float(self._config.get("cooldown", 0.15)),
            poll_interval=float(self._config.get("poll_interval", 0.001)),
            monitor_index=int(self._config.get("monitor_index", 1)),
            x=None if raw_x in (None, "") else int(raw_x),
            y=None if raw_y in (None, "") else int(raw_y),
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

        try:
            with mss() as sct:
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

                    jittered_cooldown = humanize_jitter(cfg.cooldown, fraction=_cooldown_frac if _enabled else 0.0, min_val=0.02)

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
                            pending_click_time = now + humanize_jitter(cfg.click_delay, fraction=_click_delay_frac if _enabled else 0.0, min_val=0.01)

                    humanize_sleep(cfg.poll_interval, fraction=_poll_frac if _enabled else 0.0, min_val=0.0005)
        except Exception as exc:
            self.status(str(exc), "error")
        finally:
            _safe_stop_listener(listener)
            self.status("Stopped.")
