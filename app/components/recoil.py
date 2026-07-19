from __future__ import annotations

import bisect
import ctypes
import json
import math
import os
import random
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pynput import mouse

from app.components.base import BaseComponent
from app.gsi import GameState
from app.utils.input_safety import ORIGINAL_RECOIL_MOUSE_NAME, device_name, humanize_frequency_interval, humanize_jitter

try:
    import uinput  # type: ignore
except ImportError:  # pragma: no cover
    uinput = None


PATTERNS_FILE = Path(__file__).resolve().parents[2] / "resources" / "mouse_patterns.json"


@dataclass(frozen=True)
class PatternStep:
    dx: float
    dy: float
    duration_ms: int


@dataclass(frozen=True)
class TimedPoint:
    t: float
    x: float
    y: float


@dataclass
class RuntimeSettings:
    x_strength_percent: float
    y_strength_percent: float
    sensitivity_enabled: bool
    reference_sens: float
    program_sens: float
    apply_x: bool
    apply_y: bool
    noise_strength_px: float
    return_mouse_enabled: bool
    return_mouse_delay_ms: int
    return_mouse_duration_ms: int
    return_mouse_y_percent: float

    @property
    def sensitivity_modifier(self) -> float:
        if not self.sensitivity_enabled or self.program_sens == 0:
            return 1.0
        return self.reference_sens / self.program_sens


_PATTERN_ALIASES: dict[str, str] = {
    "ak": "AK",
    "ak47": "AK",
    "weaponak47": "AK",
    "m4a1": "M4A1",
    "m4a1s": "M4A1",
    "m4a1silencer": "M4A1",
    "weaponm4a1silencer": "M4A1",
    "m4a4": "M4A4",
    "weaponm4a1": "M4A4",
    "famas": "Famas",
    "weaponfamas": "Famas",
    "galil": "Galil",
    "galilar": "Galil",
    "weapongalilar": "Galil",
    "ump": "UMP",
    "ump45": "UMP",
    "weaponump45": "UMP",
    "aug": "AUG",
    "weaponaug": "AUG",
    "sg": "SG",
    "sg553": "SG",
    "sg556": "SG",
    "weaponsg556": "SG",
}


def _canon_name(value: str) -> str:
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def _pattern_index(pattern_file: dict[str, Any]) -> dict[str, str]:
    data = pattern_file.get("patterns", {})
    return {_canon_name(actual_name): actual_name for actual_name in data}


def resolve_pattern_name(pattern_file: dict[str, Any], requested_name: str | None) -> str | None:
    if not requested_name:
        return None

    data = pattern_file.get("patterns", {})
    if requested_name in data:
        return requested_name

    index = _pattern_index(pattern_file)
    canon = _canon_name(requested_name)

    direct = index.get(canon)
    if direct is not None:
        return direct

    alias_target = _PATTERN_ALIASES.get(canon)
    if alias_target is not None:
        if alias_target in data:
            return alias_target
        alias_direct = index.get(_canon_name(alias_target))
        if alias_direct is not None:
            return alias_direct

    return None


def load_pattern_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"patterns": {}}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_settings(raw: dict[str, Any]) -> RuntimeSettings:
    ax = dict(raw.get("axis_strength_percent", {}) or {})
    sens = dict(raw.get("sensitivity", {}) or {})
    sens_ax = dict(sens.get("apply_to_axis", {}) or {})
    movement = dict(raw.get("movement", {}) or {})
    noise = dict(raw.get("noise", {}) or {})
    ret = dict(raw.get("return_mouse", {}) or {})
    return RuntimeSettings(
        x_strength_percent=float(ax.get("x", 100.0)),
        y_strength_percent=float(ax.get("y", 100.0)),
        sensitivity_enabled=bool(sens.get("enabled", True)),
        reference_sens=float(sens.get("reference_sens", 2.52)),
        program_sens=float(sens.get("program_sens", 2.52)),
        apply_x=bool(sens_ax.get("x", True)),
        apply_y=bool(sens_ax.get("y", True)),
        noise_strength_px=max(0.0, float(noise.get("strength_px", 0.0))),
        return_mouse_enabled=bool(ret.get("enabled", False)),
        return_mouse_delay_ms=max(0, int(ret.get("delay_ms", 20))),
        return_mouse_duration_ms=max(20, int(ret.get("duration_ms", 140))),
        return_mouse_y_percent=max(0.0, min(100.0, float(ret.get("y_percent", 100.0)))),
    )


def parse_pattern(pattern_file: dict[str, Any], name: str, st: RuntimeSettings, max_steps: int | None = None) -> list[PatternStep]:
    data = pattern_file.get("patterns", {})
    resolved_name = resolve_pattern_name(pattern_file, name)
    if resolved_name is None:
        available = ", ".join(sorted(data.keys())) if data else "<none>"
        raise ValueError(f"Pattern '{name}' not found in mouse_patterns.json. Available: {available}")

    raw_steps = data[resolved_name]["steps"]
    if max_steps is not None and max_steps >= 0:
        raw_steps = raw_steps[:max_steps]

    sx = st.x_strength_percent / 100.0
    sy = st.y_strength_percent / 100.0
    mod = st.sensitivity_modifier
    mod_x = mod if st.apply_x else 1.0
    mod_y = mod if st.apply_y else 1.0

    parsed: list[PatternStep] = []
    for step in raw_steps:
        dx = float(step["dx"]) * sx * mod_x
        dy = float(step["dy"]) * sy * mod_y
        dur = max(1, int(step["duration_ms"]))
        parsed.append(PatternStep(dx=dx, dy=dy, duration_ms=dur))
    return parsed


class MouseBackend:
    def __init__(self, obscure: bool = False) -> None:
        self._win = os.name == "nt"
        self._uinput_dev = None
        self._pynput_mouse = None
        self._obscure = obscure

        if self._win:
            class MOUSEINPUT(ctypes.Structure):
                _fields_ = [
                    ("dx", ctypes.c_long),
                    ("dy", ctypes.c_long),
                    ("mouseData", ctypes.c_ulong),
                    ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
                ]

            class INPUT(ctypes.Structure):
                _fields_ = [("type", ctypes.c_ulong), ("mi", MOUSEINPUT)]

            self._INPUT = INPUT
            self._MOUSEINPUT = MOUSEINPUT
            self._SendInput = ctypes.windll.user32.SendInput
            self._MOUSEEVENTF_MOVE = 0x0001
            return

        self._ensure_uinput()

    def set_obscure(self, obscure: bool) -> None:
        """Toggle obscure device name. Takes effect on next uinput device creation."""
        self._obscure = obscure

    def _ensure_uinput(self) -> None:
        if self._uinput_dev is not None:
            return
        if uinput is not None:
            try:
                self._uinput_dev = uinput.Device(
                    [uinput.BTN_LEFT, uinput.REL_X, uinput.REL_Y],
                    name=device_name(ORIGINAL_RECOIL_MOUSE_NAME, obscure=self._obscure),
                )
                time.sleep(humanize_jitter(0.05, fraction=0.3, min_val=0.02))
            except Exception:
                self._uinput_dev = None
        if self._uinput_dev is None:
            self._pynput_mouse = mouse.Controller()

    def move_relative(self, dx: int, dy: int) -> None:
        if dx == 0 and dy == 0:
            return

        if self._win:
            extra = ctypes.c_ulong(0)
            mi = self._MOUSEINPUT(
                dx=dx,
                dy=dy,
                mouseData=0,
                dwFlags=self._MOUSEEVENTF_MOVE,
                time=0,
                dwExtraInfo=ctypes.pointer(extra),
            )
            inp = self._INPUT(type=0, mi=mi)
            self._SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
            return

        if self._uinput_dev is not None:
            self._uinput_dev.emit(uinput.REL_X, dx, syn=False)
            self._uinput_dev.emit(uinput.REL_Y, dy)
        elif self._pynput_mouse is not None:
            self._pynput_mouse.move(dx, dy)


def build_timed_points(pattern: list[PatternStep]) -> list[TimedPoint]:
    pts = [TimedPoint(0.0, 0.0, 0.0)]
    t = x = y = 0.0
    for s in pattern:
        t += s.duration_ms / 1000.0
        x += s.dx
        y += s.dy
        pts.append(TimedPoint(t, x, y))
    return pts


def calc_velocities(pts: list[TimedPoint], scale: float = 1.0) -> list[tuple[float, float]]:
    n = len(pts)
    if n == 1:
        return [(0.0, 0.0)]
    out: list[tuple[float, float]] = []
    for i in range(n):
        if i == 0:
            dt = pts[1].t - pts[0].t
            vx = (pts[1].x - pts[0].x) / dt
            vy = (pts[1].y - pts[0].y) / dt
        elif i == n - 1:
            dt = pts[i].t - pts[i - 1].t
            vx = (pts[i].x - pts[i - 1].x) / dt
            vy = (pts[i].y - pts[i - 1].y) / dt
        else:
            dt0 = pts[i].t - pts[i - 1].t
            dt1 = pts[i + 1].t - pts[i].t
            vx = 0.5 * ((pts[i].x - pts[i - 1].x) / dt0 + (pts[i + 1].x - pts[i].x) / dt1)
            vy = 0.5 * ((pts[i].y - pts[i - 1].y) / dt0 + (pts[i + 1].y - pts[i].y) / dt1)
        out.append((vx * scale, vy * scale))
    return out


def hermite(p0: TimedPoint, p1: TimedPoint, v0: tuple[float, float], v1: tuple[float, float], t: float) -> tuple[float, float]:
    dt = p1.t - p0.t
    if dt <= 0:
        return p1.x, p1.y
    u = max(0.0, min(1.0, (t - p0.t) / dt))
    u2 = u * u
    u3 = u2 * u
    h00 = 2 * u3 - 3 * u2 + 1
    h10 = u3 - 2 * u2 + u
    h01 = -2 * u3 + 3 * u2
    h11 = u3 - u2
    x = h00 * p0.x + h10 * dt * v0[0] + h01 * p1.x + h11 * dt * v1[0]
    y = h00 * p0.y + h10 * dt * v0[1] + h01 * p1.y + h11 * dt * v1[1]
    return x, y


def pos_at_time(pts: list[TimedPoint], vels: list[tuple[float, float]], t: float, times: list[float]) -> tuple[float, float]:
    if t <= 0:
        return pts[0].x, pts[0].y
    if t >= pts[-1].t:
        return pts[-1].x, pts[-1].y
    idx = bisect.bisect_right(times, t) - 1
    idx = max(0, min(idx, len(pts) - 2))
    return hermite(pts[idx], pts[idx + 1], vels[idx], vels[idx + 1], t)


class SmoothMousePlayer:
    def __init__(self, owner: "RecoilComponent") -> None:
        self.owner = owner
        obscure = bool(owner._safety_config.get("obscure_device_names", False))
        self.mouse = MouseBackend(obscure=obscure)
        self._thr: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._rng = random.Random()
        self._return_thr: threading.Thread | None = None
        self._return_stop = threading.Event()

    @property
    def running(self) -> bool:
        return self._thr is not None and self._thr.is_alive()

    def cancel_return(self) -> None:
        self._return_stop.set()
        if self._return_thr is not None and self._return_thr.is_alive() and threading.current_thread() is not self._return_thr:
            self._return_thr.join(timeout=0.25)
        self._return_thr = None

    def start(self) -> None:
        if not self.owner.automation_permitted():
            return

        self.cancel_return()
        self.owner.reset_alignment_offset()

        st = self.owner.runtime_settings
        pattern_name = self.owner.current_pattern_name()
        if pattern_name is None:
            self.owner.status("No recoil pattern is available for the current weapon.", "warning")
            return

        resolved_pattern_name = resolve_pattern_name(self.owner.pattern_file, pattern_name)
        if resolved_pattern_name is None:
            available = ", ".join(sorted(self.owner.pattern_file.get("patterns", {}).keys())) or "<none>"
            self.owner.status(
                f"Pattern '{pattern_name}' was not found in mouse_patterns.json. Available: {available}",
                "error",
            )
            return

        ammo_cap = self.owner.current_ammo_cap()
        pattern = parse_pattern(self.owner.pattern_file, resolved_pattern_name, st, max_steps=ammo_cap)
        self.owner._report_pattern_status(force=True)

        with self._lock:
            if self.running:
                self._stop.set()
        if self.running and self._thr is not None:
            self._thr.join(timeout=0.3)

        self._stop.clear()
        self._thr = threading.Thread(target=self._run, args=(pattern,), daemon=True)
        self._thr.start()

    def stop(self, schedule_return: bool = False) -> None:
        self._stop.set()
        if self.running and self._thr is not None and threading.current_thread() is not self._thr:
            self._thr.join(timeout=0.35)

        self.owner.set_alignment_active(False)
        if schedule_return and self.owner.automation_permitted() and self.owner.runtime_settings.return_mouse_enabled:
            return_x, return_y = self.owner.current_alignment_vector()
            self._start_return(return_x, return_y, self.owner.runtime_settings)
        else:
            self.cancel_return()
            self.owner.reset_alignment_offset()

    def _start_return(self, offset_x: float, offset_y: float, st: RuntimeSettings) -> None:
        self.cancel_return()

        if abs(offset_x) < 0.5 and abs(offset_y) < 0.5:
            self.owner.reset_alignment_offset()
            return

        self._return_stop.clear()
        self._return_thr = threading.Thread(
            target=self._run_return,
            args=(offset_x, offset_y, st),
            daemon=True,
        )
        self._return_thr.start()

    def _run(self, pattern: list[PatternStep]) -> None:
        st = self.owner.runtime_settings
        if not self.owner.automation_permitted():
            self.owner.reset_alignment_offset()
            return
        self._play_once(pattern, st)

    def _emit_relative(self, dx: int, dy: int, track_alignment: bool) -> None:
        if dx == 0 and dy == 0:
            return
        self.mouse.move_relative(dx, dy)
        if track_alignment:
            self.owner.add_alignment_delta(dx, dy)

    def _send_bounded(self, dx: int, dy: int, track_alignment: bool = True) -> None:
        if dx == 0 and dy == 0:
            return
        limit = 3
        if limit <= 0:
            self._emit_relative(dx, dy, track_alignment)
            return
        steps = max(1, int(max(abs(dx), abs(dy)) / limit) + 1)
        sentx = senty = 0
        for i in range(1, steps + 1):
            tx = int(round(dx * i / steps))
            ty = int(round(dy * i / steps))
            self._emit_relative(tx - sentx, ty - senty, track_alignment)
            sentx, senty = tx, ty

    def _play_once(self, pattern: list[PatternStep], st: RuntimeSettings) -> None:
        pts = build_timed_points(pattern)
        vels = calc_velocities(pts)
        times = [p.t for p in pts]
        total = pts[-1].t
        step = 1.0 / 165.0

        _sf = self.owner._safety_config
        _enabled = bool(_sf.get("enabled", False))
        _step_frac = float(_sf.get("jitter_step_fraction", 0.0))
        _noise_mix_frac = float(_sf.get("jitter_noise_mix_fraction", 0.0))
        _noise_decay_frac = float(_sf.get("jitter_noise_decay_fraction", 0.0))

        self.owner.reset_alignment_offset()
        self.owner.set_alignment_active(True)
        idx = 0
        next_tick = time.perf_counter()
        lastx = lasty = resx = resy = 0.0
        noise_x = noise_y = 0.0
        noise_mix = humanize_jitter(0.22, fraction=_noise_mix_frac if _enabled else 0.0, min_val=0.10, max_val=0.40)
        noise_decay = humanize_jitter(0.78, fraction=_noise_decay_frac if _enabled else 0.0, min_val=0.60, max_val=0.90)

        while not self._stop.is_set():
            if not self.owner.automation_permitted():
                break
            logical_t = min(idx * step, total)
            tx, ty = pos_at_time(pts, vels, logical_t, times)
            movx_f = tx - lastx + resx
            movy_f = ty - lasty + resy

            if st.noise_strength_px > 0.0:
                noise_x = noise_x * noise_decay + self._rng.gauss(0.0, st.noise_strength_px) * noise_mix
                noise_y = noise_y * noise_decay + self._rng.gauss(0.0, st.noise_strength_px) * noise_mix
                movx_f += noise_x
                movy_f += noise_y

            movx = int(round(movx_f))
            movy = int(round(movy_f))
            resx = movx_f - movx
            resy = movy_f - movy
            self._send_bounded(movx, movy, track_alignment=True)
            lastx, lasty = tx, ty

            if logical_t >= total:
                break

            idx += 1
            tick_step = humanize_jitter(step, fraction=_step_frac if _enabled else 0.0, min_val=0.0005)
            next_tick += tick_step
            now = time.perf_counter()
            if next_tick < now:
                next_tick = now + tick_step
            self._sleep_until(next_tick, self._stop)

    def _run_return(self, spray_offset_x: float, spray_offset_y: float, st: RuntimeSettings) -> None:
        try:
            delay_s = max(0.0, st.return_mouse_delay_ms / 1000.0)
            if delay_s > 0.0:
                self._sleep_until(time.perf_counter() + delay_s, self._return_stop)
                if self._return_stop.is_set():
                    return

            total_dx = -float(spray_offset_x)
            total_dy = -float(spray_offset_y) * (st.return_mouse_y_percent / 100.0)
            duration_s = max(0.02, st.return_mouse_duration_ms / 1000.0)
            tick = 1.0 / 165.0
            start = time.perf_counter()
            sent_x = sent_y = 0

            while not self._return_stop.is_set():
                if not self.owner.enabled:
                    return
                elapsed = time.perf_counter() - start
                u = max(0.0, min(1.0, elapsed / duration_s))
                eased = 0.5 - 0.5 * math.cos(math.pi * u)
                want_x = int(round(total_dx * eased))
                want_y = int(round(total_dy * eased))
                move_x = want_x - sent_x
                move_y = want_y - sent_y
                if move_x or move_y:
                    self._send_bounded(move_x, move_y, track_alignment=False)
                    sent_x = want_x
                    sent_y = want_y
                if u >= 1.0:
                    break
                self._sleep_until(time.perf_counter() + tick, self._return_stop)
        finally:
            self.owner.reset_alignment_offset()

    def _sleep_until(self, target: float, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            rem = target - time.perf_counter()
            if rem <= 0:
                return
            time.sleep(min(rem, 0.001))


class MouseHoldListener:
    def __init__(self, owner: "RecoilComponent") -> None:
        self.owner = owner
        self.mouse_listener: mouse.Listener | None = None

    def start(self) -> None:
        self.mouse_listener = mouse.Listener(on_click=self._on_click)
        self.mouse_listener.start()

    def stop(self) -> None:
        self.owner.player.stop(schedule_return=False)
        if self.mouse_listener is not None:
            with suppress(Exception):
                self.mouse_listener.stop()
            self.mouse_listener = None

    def _on_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        if button != mouse.Button.left:
            return
        self.owner.set_mouse1_held(pressed)
        if pressed:
            self._safe_start_player()
        else:
            self.owner.player.stop(schedule_return=True)

    def _safe_start_player(self) -> None:
        if not self.owner.automation_permitted():
            return
        try:
            self.owner.player.start()
        except Exception as exc:
            self.owner.status(str(exc), "error")


class RecoilComponent(BaseComponent):
    name = "recoil"

    def __init__(self) -> None:
        super().__init__()
        self.runtime_settings = parse_settings({})
        self.pattern_file: dict[str, Any] = {"patterns": {}}
        self._safety_config: dict[str, Any] = {}
        self.player = SmoothMousePlayer(self)
        self.listener: MouseHoldListener | None = None
        self._current_weapon: str | None = None
        self._current_ammo_clip: int | None = None
        self._last_pattern_status = ""
        self._align_lock = threading.RLock()
        self._mouse1_held = False
        self._alignment_mouse_x = 0.0
        self._alignment_mouse_y = 0.0
        self._alignment_active = False


    def set_mouse1_held(self, held: bool) -> None:
        with self._align_lock:
            self._mouse1_held = bool(held)

    def set_alignment_active(self, active: bool) -> None:
        with self._align_lock:
            self._alignment_active = bool(active)

    def add_alignment_delta(self, dx: float, dy: float) -> None:
        with self._align_lock:
            self._alignment_mouse_x += float(dx)
            self._alignment_mouse_y += float(dy)
            self._alignment_active = True

    def current_alignment_vector(self) -> tuple[float, float]:
        with self._align_lock:
            return self._alignment_mouse_x, self._alignment_mouse_y

    def reset_alignment_offset(self) -> None:
        with self._align_lock:
            self._alignment_active = False
            self._alignment_mouse_x = 0.0
            self._alignment_mouse_y = 0.0

    def get_alignment_state(self) -> dict[str, Any]:
        with self._align_lock:
            return {
                "mouse1_held": self._mouse1_held,
                "active": self._alignment_active and self._mouse1_held and self.enabled and self.automation_permitted(),
                "mouse_offset_x": self._alignment_mouse_x,
                "mouse_offset_y": self._alignment_mouse_y,
                "weapon": self._current_weapon,
                "ammo_clip": self._current_ammo_clip,
            }

    def configure(self, config: dict[str, Any]) -> None:
        super().configure(config)
        self.runtime_settings = parse_settings(config)
        self.pattern_file = load_pattern_file(PATTERNS_FILE)
        self._safety_config = dict(config.get("_safety", {}))
        obscure = bool(self._safety_config.get("obscure_device_names", False))
        self.player.mouse.set_obscure(obscure)
        self._report_pattern_status(force=True)

    def start(self) -> None:
        super().start()
        if self.listener is not None:
            self.listener.stop()
        self.listener = MouseHoldListener(self)
        self.listener.start()
        self.status(f"Started. Recoil is active while left mouse is held. Patterns file: {PATTERNS_FILE}")
        self._report_pattern_status(force=True)

    def stop(self) -> None:
        super().stop()
        self.player.stop(schedule_return=False)
        self.reset_alignment_offset()
        self.set_mouse1_held(False)
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
        self.status("Stopped.")

    def on_runtime_gate_changed(self, open_: bool, reason: str) -> None:
        if not open_:
            self.player.stop(schedule_return=False)
            self.reset_alignment_offset()
        self._report_pattern_status(force=True)

    def current_pattern_name(self) -> str | None:
        return resolve_pattern_name(self.pattern_file, self._current_weapon)

    def current_ammo_cap(self) -> int | None:
        return self._current_ammo_clip

    def _pattern_status_text(self) -> str:
        if self._current_weapon is None:
            return "Active pattern: none (weapon unknown)"

        resolved = self.current_pattern_name()
        if not self.runtime_gate_open():
            return f"Active pattern: {resolved or 'none'} (weapon={self._current_weapon}; gated)"
        if resolved is None:
            return f"Active pattern: none (weapon={self._current_weapon}; unsupported)"
        ammo_text = "?" if self._current_ammo_clip is None else str(self._current_ammo_clip)
        return f"Active pattern: {resolved} (weapon={self._current_weapon}; clip={ammo_text})"

    def _report_pattern_status(self, force: bool = False) -> None:
        message = self._pattern_status_text()
        if force or message != self._last_pattern_status:
            self._last_pattern_status = message
            self.status(message)

    def on_gsi_state(self, state: GameState) -> None:
        self._current_weapon = state.current_weapon
        self._current_ammo_clip = state.ammo_clip
        if not state.features_allowed:
            self.player.stop(schedule_return=False)
            self.reset_alignment_offset()
        self._report_pattern_status()
