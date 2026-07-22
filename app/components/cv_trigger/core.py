from __future__ import annotations

import threading
import time
import json
import os
from pathlib import Path
from typing import Any

from app.components.base import BaseComponent
from app.gsi import GameState

from . import aim_motion
from .curve_config import build_curve_library
from .activation import (
    ActivationState,
    button_to_name,
    canonical_weapon_name,
    key_to_name,
)
from .capture import Grab
from .detection import PositionSmoother, ScopeDetector, scope_corner_capture_regions
from .inference import InferenceConfig, UltralyticsInferenceEngine
from .input_worker import InputWorker
from .metrics import CVPerfStats
from .migration import _migrate_legacy_config
from .post_shot_y import (
    ConfirmedShotEvent,
    PostShotYSuppression,
    ShotEventTracker,
    ShotStartEvent,
    clamp_positive_y_to_limit,
    clamp_x_to_limit,
    post_shot_config_from_mapping,
)
from .roi import CaptureRegion, compute_center_roi
from .runtime_rules import compile_rules, highest_priority_rules
from .patterns import (
    PATTERNS_FILE,
    _CLASS_INDEX_BY_SIDE_AND_TYPE,
    _extract_player_side_from_payload,
    _load_pattern_file,
    _scaled_recoil_pattern_steps,
    _truthy,
)
from .postprocess import extract_filtered_detections
from .virtual_mouse import VirtualMouse
from .weapon_recoil import load_weapon_recoil_table, weapon_recoil_info


def _safe_stop_listener(listener: Any) -> None:
    if listener is None:
        return
    try:
        listener.stop()
    except Exception:
        return


def _aim_point_for_box(
    *,
    box: tuple[int, int, int, int],
    crosshair: tuple[int, int],
    aim_mode: str,
    head_offset: float,
    body_knee_offset: float,
) -> tuple[int, int]:
    x1, y1, x2, y2 = box
    _, cy = crosshair
    tx = (x1 + x2) >> 1
    if aim_mode == "head":
        return tx, int(y1 + head_offset * (y2 - y1))

    knee = int(y1 + body_knee_offset * (y2 - y1))
    provisional = min(max(cy, y1), y2)
    return tx, provisional if provisional < knee else knee


def _body_y_axis_is_loose(
    *,
    box: tuple[int, int, int, int],
    crosshair: tuple[int, int],
    aim_mode: str,
    body_knee_offset: float,
) -> bool:
    if aim_mode != "body":
        return False
    _, y1, _, y2 = box
    _, cy = crosshair
    knee = int(y1 + body_knee_offset * (y2 - y1))
    return y1 <= cy <= knee


def _raw_aim_error(
    *,
    target: tuple[float, float],
    predicted_bullet: tuple[float, float],
    body_y_axis_loose: bool,
) -> tuple[float, float]:
    raw_x = target[0] - predicted_bullet[0]
    raw_y = 0.0 if body_y_axis_loose else target[1] - predicted_bullet[1]
    return raw_x, raw_y


def _lock_body_y_axis(error_px: tuple[float, float], *, body_y_axis_loose: bool) -> tuple[float, float]:
    if body_y_axis_loose:
        return error_px[0], 0.0
    return error_px


def _rule_priority(rule: dict[str, Any]) -> int:
    try:
        return int(rule.get("priority", 0))
    except (TypeError, ValueError):
        return 0


def _highest_priority_rule_names(configs: dict[str, dict[str, Any]], active_names: list[str]) -> list[str]:
    if not active_names:
        return []
    highest = max(_rule_priority(configs[name]) for name in active_names)
    return [name for name in active_names if _rule_priority(configs[name]) == highest]


def _sum_motion_counts(motions: list[aim_motion.AimMotionResult]) -> tuple[int, int]:
    return sum(motion.dx for motion in motions), sum(motion.dy for motion in motions)


def _auto_shoot_zone_contains_crosshair(
    *,
    box: tuple[int, int, int, int],
    crosshair: tuple[int, int],
    zone_width: int,
    zone_height: int,
    zone_y_pos: float,
) -> bool:
    x1, y1, x2, y2 = box
    cx, cy = crosshair
    box_cx = (x1 + x2) >> 1
    box_h = y2 - y1
    if box_h <= 0:
        return False
    zone_cy = y1 + int(box_h * zone_y_pos)
    half_w = zone_width >> 1
    half_h = zone_height >> 1
    return (box_cx - half_w <= cx <= box_cx + half_w and
            zone_cy - half_h <= cy <= zone_cy + half_h)


def _shot_cooldown_active(*, now: float, cooldown_until: float) -> bool:
    return now < cooldown_until


def _curve_points_for_rule(aim_curves: dict[str, Any], curve_id: str) -> list[aim_motion.CurvePoint]:
    curve = aim_curves.get(curve_id)
    if not isinstance(curve, dict):
        curve = aim_curves.get("linear")

    points_raw = curve.get("points") if isinstance(curve, dict) else None
    points: list[aim_motion.CurvePoint] = []
    if isinstance(points_raw, list):
        for point in points_raw:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                try:
                    points.append((float(point[0]), float(point[1])))
                except (TypeError, ValueError):
                    continue

    if len(points) < 2:
        linear = build_curve_library()["linear"]["points"]
        return [(float(point[0]), float(point[1])) for point in linear]
    return sorted(points, key=lambda item: item[0])


def _smoothed_error_for_rule(
    *,
    rule_name: str,
    error_px: tuple[float, float],
    smoothing_alpha: float,
    per_rule_smooth: dict[str, tuple[float, float] | None],
) -> tuple[float, float]:
    previous = per_rule_smooth.get(rule_name)
    if smoothing_alpha > 0.0 and previous is not None:
        smoothed = (
            previous[0] + smoothing_alpha * (error_px[0] - previous[0]),
            previous[1] + smoothing_alpha * (error_px[1] - previous[1]),
        )
    else:
        smoothed = error_px
    per_rule_smooth[rule_name] = smoothed
    return smoothed


def _raw_error_sign(error_px: tuple[float, float], deadzone_px: float) -> tuple[int, int]:
    def axis_sign(value: float) -> int:
        if abs(value) <= deadzone_px:
            return 0
        return 1 if value > 0.0 else -1

    return axis_sign(error_px[0]), axis_sign(error_px[1])


def _anti_oscillation_reversal_lock_frames(
    *,
    previous_sign: tuple[int, int] | None,
    current_sign: tuple[int, int],
    distance_px: float,
    radius_px: float,
    lock_frames: int,
) -> int:
    if previous_sign is None or radius_px <= 0.0 or lock_frames <= 0 or distance_px > radius_px:
        return 0
    x_reversed = previous_sign[0] != 0 and current_sign[0] != 0 and previous_sign[0] != current_sign[0]
    y_reversed = previous_sign[1] != 0 and current_sign[1] != 0 and previous_sign[1] != current_sign[1]
    return lock_frames if x_reversed or y_reversed else 0


def _full_capture_region(monitor: dict[str, int]) -> CaptureRegion:
    return CaptureRegion(
        monitor_left=int(monitor.get("left", 0)),
        monitor_top=int(monitor.get("top", 0)),
        roi_left=0,
        roi_top=0,
        width=max(1, int(monitor.get("width", 1))),
        height=max(1, int(monitor.get("height", 1))),
    )


def _capture_region_for_config(
    *,
    monitor: dict[str, int],
    enabled_configs: dict[str, dict[str, Any]],
    inference_img_size: int,
    config: dict[str, Any],
) -> CaptureRegion:
    mode = str(config.get("capture_mode", "auto") or "auto").strip().lower()
    if mode == "full" or mode not in {"auto", "roi"}:
        return _full_capture_region(monitor)

    snap_values: list[int] = []
    zone_values: list[int] = []
    for item in enabled_configs.values():
        snap_values.append(max(0, int(item.get("SNAP_DISTANCE", 200) or 200)))
        zone_values.append(max(0, int(item.get("AUTO_SHOOT_ZONE_WIDTH", 28) or 28)))
        zone_values.append(max(0, int(item.get("AUTO_SHOOT_ZONE_HEIGHT", 36) or 36)))
    max_snap_distance = max(snap_values) if snap_values else 200
    default_padding = max(96, max(zone_values) if zone_values else 0, int(max_snap_distance * 0.5))
    roi_padding_px = int(config.get("roi_padding_px", default_padding) or default_padding)
    roi_min_size_px = int(config.get("roi_min_size_px", inference_img_size) or inference_img_size)
    raw_max_size = config.get("roi_max_size_px")
    roi_max_size_px = None if raw_max_size in (None, "") else int(raw_max_size)
    return compute_center_roi(
        monitor=monitor,
        max_snap_distance=max_snap_distance,
        inference_img_size=inference_img_size,
        roi_padding_px=roi_padding_px,
        roi_min_size_px=roi_min_size_px,
        roi_max_size_px=roi_max_size_px,
    )


def _should_note_manual_release_candidate(*, pressed_at: float, released_at: float, max_hold_seconds: float) -> bool:
    held_seconds = released_at - pressed_at
    return 0.0 <= held_seconds <= max_hold_seconds


class CVTriggerComponent(BaseComponent):
    name = "cv_trigger"

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._gsi_lock = threading.RLock()
        self._current_weapon: str | None = None
        self._ammo_clip: int | None = None
        self._ammo_clip_max: int | None = None
        self._shots_fired: int | None = None
        self._last_shots_change_at: float | None = None
        self._current_player_side: str | None = None
        self._last_kills: int | None = None
        self._pending_kill_event: bool = False
        self._post_shot_config = post_shot_config_from_mapping(None)
        self._shot_tracker = ShotEventTracker(self._post_shot_config)
        self._post_shot_events: list[ShotStartEvent | ConfirmedShotEvent] = []
        self._post_shot_reset_pending = False
        self._overlay_lock = threading.RLock()
        self._overlay_active = False
        self._overlay_offset_x = 0.0
        self._overlay_offset_y = 0.0
        self._overlay_rule_name: str | None = None

    def configure(self, config: dict[str, Any]) -> None:
        migrated = _migrate_legacy_config(config)
        super().configure(migrated)
        self._configure_post_shot_state(migrated)

    def _configure_post_shot_state(self, config: dict[str, Any]) -> None:
        post_shot_config = post_shot_config_from_mapping(config.get("post_shot_y_suppression"))
        with self._gsi_lock:
            self._post_shot_config = post_shot_config
            self._shot_tracker = ShotEventTracker(post_shot_config)
            self._post_shot_events.clear()
            self._post_shot_reset_pending = True

    def on_gsi_state(self, state: GameState) -> None:
        now = time.perf_counter()
        with self._gsi_lock:
            weapon_changed = state.current_weapon != self._current_weapon
            self._current_weapon = state.current_weapon
            self._ammo_clip = state.ammo_clip
            self._ammo_clip_max = state.ammo_clip_max
            self._current_player_side = _extract_player_side_from_payload(getattr(state, "raw", None))

            if state.ammo_clip is None or state.ammo_clip_max is None:
                new_shots_fired = None
            else:
                new_shots_fired = max(0, int(state.ammo_clip_max) - int(state.ammo_clip))

            if self._post_shot_config.enabled:
                recoil_state = self._runtime_recoil_alignment_state()
                recoil_active = bool(recoil_state is not None and recoil_state.get("active", False))
                update = self._shot_tracker.update_gsi_weapon_ammo(
                    state.current_weapon,
                    state.ammo_clip,
                    state.ammo_clip_max,
                    now,
                    recoil_active=recoil_active,
                )
                if update.cancel_provisional:
                    self._post_shot_reset_pending = True
                if update.confirmed is not None and update.should_start_suppression:
                    self._post_shot_events.append(update.confirmed)

            if weapon_changed or new_shots_fired != self._shots_fired:
                self._last_shots_change_at = now
            self._shots_fired = new_shots_fired

            # Track kills via GSI match_stats — set a flag when kills increase
            new_kills = state.kills
            if new_kills is not None:
                if self._last_kills is not None and new_kills > self._last_kills:
                    self._pending_kill_event = True
                self._last_kills = new_kills

    def _consume_kill_event(self) -> bool:
        """Check and clear the pending kill event flag (thread-safe)."""
        with self._gsi_lock:
            if self._pending_kill_event:
                self._pending_kill_event = False
                return True
            return False

    def _note_post_shot_manual_candidate(self) -> None:
        with self._gsi_lock:
            if not self._post_shot_config.enabled:
                return
            event = self._shot_tracker.note_manual_press(self._current_weapon, time.perf_counter())
            self._post_shot_events.append(event)

    def _note_post_shot_cv_auto_candidate(self) -> None:
        with self._gsi_lock:
            if not self._post_shot_config.enabled:
                return
            event = self._shot_tracker.note_cv_auto_click(self._current_weapon, time.perf_counter())
            self._post_shot_events.append(event)

    def _consume_post_shot_updates(self) -> tuple[list[ShotStartEvent | ConfirmedShotEvent], bool]:
        with self._gsi_lock:
            events = list(self._post_shot_events)
            self._post_shot_events.clear()
            reset_pending = self._post_shot_reset_pending
            self._post_shot_reset_pending = False
            return events, reset_pending

    def _reset_post_shot_state(self) -> None:
        with self._gsi_lock:
            self._shot_tracker.reset()
            self._post_shot_events.clear()
            self._post_shot_reset_pending = True

    def on_runtime_gate_changed(self, open_: bool, reason: str) -> None:
        if not open_:
            self._reset_post_shot_state()

    def _current_weapon_name(self) -> str | None:
        with self._gsi_lock:
            return self._current_weapon

    def _current_player_side_name(self) -> str | None:
        with self._gsi_lock:
            return self._current_player_side

    def _set_overlay_state(self, active: bool, offset_x: float = 0.0, offset_y: float = 0.0, rule_name: str | None = None) -> None:
        with self._overlay_lock:
            self._overlay_active = bool(active)
            self._overlay_offset_x = float(offset_x)
            self._overlay_offset_y = float(offset_y)
            self._overlay_rule_name = rule_name

    def get_bullet_overlay_state(self) -> dict[str, Any]:
        with self._overlay_lock:
            return {
                "active": self._overlay_active and self.enabled and self.automation_permitted(),
                "offset_x": self._overlay_offset_x,
                "offset_y": self._overlay_offset_y,
                "rule_name": self._overlay_rule_name,
            }

    def _runtime_recoil_alignment_state(self) -> dict[str, Any] | None:
        provider = self._config.get("recoil_runtime_provider")
        if not callable(provider):
            return None
        try:
            state = provider()
        except Exception:
            return None
        if not isinstance(state, dict):
            return None
        return state

    def _current_recoil_state(self) -> tuple[str | None, int | None, int | None, int | None, float | None]:
        with self._gsi_lock:
            return (
                self._current_weapon,
                self._ammo_clip,
                self._ammo_clip_max,
                self._shots_fired,
                self._last_shots_change_at,
            )

    def _global_target_sides(self, config: dict[str, Any]) -> set[str]:
        if _truthy(config.get("use_gsi_opponent_side", False)):
            player_side = self._current_player_side_name()
            if player_side == "t":
                return {"ct"}
            if player_side == "ct":
                return {"t"}
            return set()

        manual = str(config.get("manual_target_side", "both") or "both").strip().lower()
        if manual in {"terrorist", "terrorists", "t"}:
            return {"t"}
        if manual in {"counter_terrorist", "counter_terrorists", "counterterrorists", "counter-terrorists", "ct"}:
            return {"ct"}
        return {"t", "ct"}

    def _resolve_rule_target_classes(self, cfg: dict[str, Any], global_target_sides: set[str]) -> set[int]:
        if not global_target_sides:
            return set()

        target_type = str(cfg.get("target_type", "both") or "both").strip().lower()
        if target_type in {"type1", "body", "tc"}:
            types = ("type1",)
        elif target_type in {"type2", "head", "thch"}:
            types = ("type2",)
        else:
            types = ("type1", "type2")

        classes: set[int] = set()
        for side in global_target_sides:
            mapping = _CLASS_INDEX_BY_SIDE_AND_TYPE.get(side, {})
            for type_name in types:
                class_idx = mapping.get(type_name)
                if class_idx is not None:
                    classes.add(class_idx)
        return classes

    def _spray_target_offset_for_rule(
        self,
        cfg: dict[str, Any],
        pattern_file: dict[str, Any],
        recoil_sync: dict[str, Any],
        fallback_program_sens: float,
        left_button_held: bool,
    ) -> tuple[float, float]:
        if not _truthy(cfg.get("spray_target_offset_enabled", False)):
            return 0.0, 0.0
        if not left_button_held:
            return 0.0, 0.0

        screen_scale = float(
            recoil_sync.get(
                "screen_space_scale",
                dict(recoil_sync.get("overlay", {}) or {}).get("screen_scale", 0.30),
            )
            or 0.30
        )

        base_sens_mult_x = round(
            (int(self._config.get("game_resolution", {}).get("width", 1600)) / max(1, int(self._config.get("monitor", {}).get("width", 2560))))
            / max(float(self._config.get("user_sens", fallback_program_sens) or fallback_program_sens), 1e-6),
            4,
        )
        base_sens_mult_y = round(
            (int(self._config.get("game_resolution", {}).get("height", 1200)) / max(1, int(self._config.get("monitor", {}).get("height", 1440))))
            / max(float(self._config.get("user_sens", fallback_program_sens) or fallback_program_sens), 1e-6),
            4,
        )

        runtime_state = self._runtime_recoil_alignment_state()
        if runtime_state is not None:
            runtime_held = bool(runtime_state.get("mouse1_held", False))
            runtime_active = bool(runtime_state.get("active", False))
            if runtime_held and runtime_active:
                mouse_x = float(runtime_state.get("mouse_offset_x", 0.0) or 0.0)
                mouse_y = float(runtime_state.get("mouse_offset_y", 0.0) or 0.0)
                denom_x = base_sens_mult_x if abs(base_sens_mult_x) > 1e-6 else 1.0
                denom_y = base_sens_mult_y if abs(base_sens_mult_y) > 1e-6 else 1.0
                return (mouse_x / denom_x) * screen_scale, (mouse_y / denom_y) * screen_scale
            return 0.0, 0.0

        if not _truthy(recoil_sync.get("enabled", False)):
            return 0.0, 0.0

        current_weapon, ammo_clip, ammo_clip_max, shots_fired, last_change_at = self._current_recoil_state()
        if current_weapon is None or ammo_clip is None or ammo_clip_max is None or shots_fired is None:
            return 0.0, 0.0
        if shots_fired <= 0:
            return 0.0, 0.0

        steps = _scaled_recoil_pattern_steps(pattern_file, current_weapon, recoil_sync, fallback_program_sens)
        if not steps:
            return 0.0, 0.0

        step_index = min(shots_fired, len(steps)) - 1
        if step_index < 0:
            return 0.0, 0.0

        recoil_mouse_x = 0.0
        recoil_mouse_y = 0.0
        for dx, dy, _ in steps[:step_index]:
            recoil_mouse_x += dx
            recoil_mouse_y += dy

        current_dx, current_dy, current_duration_ms = steps[step_index]
        progress = 1.0
        if last_change_at is not None and current_duration_ms > 0:
            progress = min(1.0, max(0.0, (time.perf_counter() - last_change_at) / (current_duration_ms / 1000.0)))
        recoil_mouse_x += current_dx * progress
        recoil_mouse_y += current_dy * progress

        denom_x = base_sens_mult_x if abs(base_sens_mult_x) > 1e-6 else 1.0
        denom_y = base_sens_mult_y if abs(base_sens_mult_y) > 1e-6 else 1.0
        return (recoil_mouse_x / denom_x) * screen_scale, (recoil_mouse_y / denom_y) * screen_scale

    def _scope_allowed(self, cfg: dict[str, Any], scoped_visual: bool) -> bool:
        requirement = cfg.get("only_when_scoped_visual", cfg.get("only_when_scoped", False))
        if not _truthy(requirement):
            return True
        return bool(scoped_visual)

    def _weapon_allowed(self, cfg: dict[str, Any]) -> bool:
        restrictions = cfg.get("allowed_weapons", cfg.get("only_when_weapon"))
        if restrictions in (None, "", []):
            return True

        if isinstance(restrictions, str):
            wanted = [restrictions]
        elif isinstance(restrictions, (list, tuple, set)):
            wanted = [str(item) for item in restrictions if str(item).strip()]
        else:
            wanted = [str(restrictions)]

        current_weapon = self._current_weapon_name()
        if not current_weapon:
            return False

        current_canon = canonical_weapon_name(current_weapon)
        allowed = {canonical_weapon_name(item) for item in wanted}
        return current_canon in allowed

    def start(self) -> None:
        super().start()
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        super().stop()
        self._stop.set()
        self._reset_post_shot_state()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self.status("Stopping.")

    def _run(self) -> None:
        try:
            import numpy as np
            import cv2
            import mss
            import torch
            from pynput import keyboard, mouse
            from ultralytics import YOLO
        except Exception as exc:
            self.status(f"ultralytics import failed: {exc}", "error")
            self._thread = None
            return

        config = _migrate_legacy_config(dict(self._config))
        model_path = Path(str(config.get("model_path", "")))
        if not model_path.exists():
            self.status(f"Model not found: {model_path}", "error")
            self._thread = None
            return

        monitor = dict(config.get("monitor", {"top": 0, "left": 0, "width": 2560, "height": 1440}))
        game_resolution = dict(config.get("game_resolution", {"width": 1600, "height": 1200}))
        user_sens = float(config.get("user_sens", 1.0))
        raw_configs = dict(config.get("configs", {}))
        enabled_configs = {name: dict(item) for name, item in raw_configs.items() if _truthy(item.get("enabled", True))}
        if not enabled_configs:
            self.status("No enabled CV configs.", "warning")
            self._thread = None
            return
        aim_curves = dict(config.get("aim_curves", {}) or {})
        compiled_rules = compile_rules(enabled_configs, aim_curves)

        pattern_file = _load_pattern_file(PATTERNS_FILE)
        weapon_recoil_table = load_weapon_recoil_table()
        recoil_sync = dict(config.get("recoil_sync", {}) or {})
        post_shot_config = post_shot_config_from_mapping(config.get("post_shot_y_suppression"))
        post_shot_suppressor = PostShotYSuppression(post_shot_config)
        inference_confidence = float(config.get("inference_confidence", 0.15) or 0.15)
        inference_img_size = int(config.get("inference_img_size", 384) or 384)
        jitter_deadzone_px = float(config.get("jitter_deadzone_px", 2.0) or 2.0)
        near_smoothing_alpha = float(config.get("near_smoothing_alpha", 0.35) or 0.35)
        near_smoothing_alpha = max(0.05, min(1.0, near_smoothing_alpha))
        near_smoothing_radius_px = float(config.get("near_smoothing_radius_px", 32.0) or 32.0)
        position_smoothing_frames = max(1, int(config.get("position_smoothing_frames", 3) or 3))
        anti_oscillation_radius_raw = config.get("anti_oscillation_radius_px", 24.0)
        anti_oscillation_reserve_raw = config.get("anti_oscillation_reserve_counts", 1)
        anti_oscillation_lock_raw = config.get("anti_oscillation_lock_frames", 2)
        anti_oscillation_radius_px = max(0.0, float(24.0 if anti_oscillation_radius_raw is None else anti_oscillation_radius_raw))
        anti_oscillation_reserve_counts = max(0, int(1 if anti_oscillation_reserve_raw is None else anti_oscillation_reserve_raw))
        anti_oscillation_lock_frames = max(0, int(2 if anti_oscillation_lock_raw is None else anti_oscillation_lock_raw))
        perf_enabled = _truthy(config.get("perf_enabled", False)) or os.environ.get("CS2_ASSIST_CV_PERF") == "1"
        perf_stats = CVPerfStats(enabled=perf_enabled)
        perf_output_path = str(config.get("perf_output_path", "") or os.environ.get("CS2_ASSIST_CV_PERF_OUT", ""))

        try:
            vmouse = VirtualMouse()
        except Exception as exc:
            self.status(str(exc), "error")
            self._thread = None
            return
        input_worker = InputWorker(vmouse)
        input_worker.start()

        model = YOLO(str(model_path))
        device = 0 if torch.cuda.is_available() else "cpu"
        if device == 0:
            half_model = getattr(getattr(model, "model", None), "half", None)
            if callable(half_model):
                half_model()
        inference_engine = UltralyticsInferenceEngine(
            model=model,
            config=InferenceConfig(
                confidence=inference_confidence,
                image_size=inference_img_size,
                device=device,
            ),
        )

        mon_width = int(monitor["width"])
        mon_height = int(monitor["height"])
        game_width = int(game_resolution["width"])
        game_height = int(game_resolution["height"])
        cx = mon_width // 2
        cy = mon_height // 2
        capture_region = _capture_region_for_config(
            monitor=monitor,
            enabled_configs=enabled_configs,
            inference_img_size=inference_img_size,
            config=config,
        )
        try:
            with perf_stats.timer("inference_warmup_ms"):
                inference_engine.warmup(
                    np.zeros((capture_region.height, capture_region.width, 3), dtype=np.uint8),
                )
        except StopIteration:
            self.status("CV inference warmup returned no result; continuing without warmup result.", "warning")
        except RuntimeError as exc:
            self.status(f"CV inference warmup failed: {exc}", "warning")

        per_rule_smooth: dict[str, tuple[float, float] | None] = {}

        activation = ActivationState()
        left_pressed_at: float | None = None
        manual_release_max_hold_seconds = post_shot_config.manual_release_max_hold_ms / 1000.0

        def on_press(key, *args) -> None:
            activation.press_key(key_to_name(key))

        def on_release(key, *args) -> None:
            activation.release_key(key_to_name(key))

        def on_click(x, y, button, pressed, *args) -> None:
            nonlocal left_pressed_at
            name = button_to_name(button)
            if pressed:
                activation.press_button(name)
                if name == "left":
                    left_pressed_at = time.perf_counter()
            else:
                if name == "left" and left_pressed_at is not None:
                    released_at = time.perf_counter()
                    if _should_note_manual_release_candidate(
                        pressed_at=left_pressed_at,
                        released_at=released_at,
                        max_hold_seconds=manual_release_max_hold_seconds,
                    ):
                        self._note_post_shot_manual_candidate()
                    left_pressed_at = None
                activation.release_button(name)

        key_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        mouse_listener = mouse.Listener(on_click=on_click)
        key_listener.start()
        mouse_listener.start()

        grab = Grab(monitor, status_callback=self.status, region=capture_region, perf_stats=perf_stats)
        grab.start()

        scope_detector = ScopeDetector()
        requires_visual_scope = any(rule.requires_scope for rule in compiled_rules.values())
        scope_capture_regions = scope_corner_capture_regions(monitor, scope_detector.patch_size) if requires_visual_scope else ()
        scope_capture = None
        pos_smoother = PositionSmoother(alpha=2.0 / (max(1, int(position_smoothing_frames)) + 1.0))

        settle: dict[str, int] = {name: 0 for name in enabled_configs}
        cooldown_until: dict[str, float] = {name: 0.0 for name in enabled_configs}
        aim_cooldown_until: dict[str, float] = {name: 0.0 for name in enabled_configs}
        filtered_error: dict[str, tuple[float, float] | None] = {name: None for name in enabled_configs}
        raw_error_signs: dict[str, tuple[int, int] | None] = {name: None for name in enabled_configs}
        reversal_locks: dict[str, int] = {name: 0 for name in enabled_configs}
        previous_active: tuple[str, ...] = ()
        status_every = 0.0
        run_started = time.perf_counter()
        frames_processed = 0
        self.status("Started.")

        try:
            scope_capture = mss.mss() if requires_visual_scope else None
            while not self._stop.is_set():
                with perf_stats.timer("loop_wait_ms"):
                    frame_info = grab.next_frame(timeout=0.1)
                if frame_info is None:
                    continue
                frame_started_ns = time.perf_counter_ns()
                frames_processed += 1
                frame = frame_info.data
                frame_age_ms = (frame_started_ns - frame_info.captured_at_ns) / 1_000_000.0
                if perf_stats.enabled:
                    perf_stats.record_ms("frame_age_ms", frame_age_ms)
                with perf_stats.timer("preprocess_ms"):
                    pass

                if not self.automation_permitted():
                    for name in settle:
                        settle[name] = 0
                        filtered_error[name] = None
                        aim_cooldown_until[name] = 0.0
                        per_rule_smooth.pop(name, None)
                        raw_error_signs[name] = None
                        reversal_locks[name] = 0
                    pos_smoother.reset_many(settle.keys())
                    previous_active = ()
                    self._set_overlay_state(False)
                    post_shot_suppressor.reset()
                    time.sleep(0.01)
                    if perf_stats.enabled:
                        perf_stats.record_ms("end_to_end_ms", (time.perf_counter_ns() - frame_started_ns) / 1_000_000.0)
                    continue

                if (
                    post_shot_config.enabled
                    and post_shot_config.max_frame_age_ms > 0
                    and frame_age_ms > post_shot_config.max_frame_age_ms
                ):
                    post_shot_suppressor.reset()
                    per_rule_smooth.clear()
                    for name in settle:
                        settle[name] = 0
                        filtered_error[name] = None
                        raw_error_signs[name] = None
                        reversal_locks[name] = 0
                    pos_smoother.reset_many(settle.keys())
                    self._set_overlay_state(False)
                    if perf_stats.enabled:
                        perf_stats.record_ms("end_to_end_ms", (time.perf_counter_ns() - frame_started_ns) / 1_000_000.0)
                    continue

                post_shot_events, post_shot_reset = self._consume_post_shot_updates()
                if post_shot_reset:
                    post_shot_suppressor.reset()
                for post_shot_event in post_shot_events:
                    post_shot_suppressor.start(
                        post_shot_event,
                        weapon_recoil_info(weapon_recoil_table, post_shot_event.weapon),
                    )

                with perf_stats.timer("rule_select_ms"):
                    current_weapon = self._current_weapon_name()
                    scoped_visual = False
                    rules_matching_without_scope = [
                        rule
                        for rule in compiled_rules.values()
                        if activation.is_active(rule.activation)
                        and rule.weapon_allowed(current_weapon)
                    ]
                    if any(rule.requires_scope for rule in rules_matching_without_scope):
                        with perf_stats.timer("scope_sample_ms"):
                            if capture_region.roi_left == 0 and capture_region.roi_top == 0 and capture_region.width == mon_width and capture_region.height == mon_height:
                                scoped_visual = scope_detector.update(frame)
                            elif scope_capture is not None:
                                scoped_visual = scope_detector.update_patches(
                                    tuple(
                                        cv2.cvtColor(np.asarray(scope_capture.grab(region), np.uint8), cv2.COLOR_BGRA2BGR)
                                        for region in scope_capture_regions
                                    ),
                                )
                    global_target_sides = self._global_target_sides(config)

                    active_rules = highest_priority_rules([rule for rule in rules_matching_without_scope if rule.scope_allowed(scoped_visual)])
                    active_names = [rule.name for rule in active_rules]
                active_name_set = set(active_names)
                for name in enabled_configs:
                    if name not in active_name_set:
                        settle[name] = 0
                        filtered_error[name] = None
                        aim_cooldown_until[name] = 0.0
                        per_rule_smooth.pop(name, None)
                        raw_error_signs[name] = None
                        reversal_locks[name] = 0
                        pos_smoother.reset(name)

                if tuple(active_names) != previous_active:
                    previous_active = tuple(active_names)
                    if time.time() >= status_every:
                        if active_names:
                            weapon_text = current_weapon or "<unknown>"
                            target_side_text = ",".join(sorted(global_target_sides)) if global_target_sides else "<none>"
                            self.status(f"Active CV config(s): {', '.join(active_names)} | weapon={weapon_text} | targets={target_side_text}")
                        else:
                            self.status(f"No active CV config matched. weapon={current_weapon or '<unknown>'}")
                        status_every = time.time() + 0.25

                if not active_names:
                    self._set_overlay_state(False)
                    if post_shot_config.enabled:
                        post_shot_suppressor.note_target_missing(time.perf_counter())
                    if perf_stats.enabled:
                        perf_stats.record_ms("end_to_end_ms", (time.perf_counter_ns() - frame_started_ns) / 1_000_000.0)
                    continue

                active_target_classes: set[int] = set()
                for rule in active_rules:
                    active_target_classes.update(rule.target_classes(global_target_sides))

                # Detect kill via GSI and apply aim cooldown to all active rules
                if self._consume_kill_event():
                    _now = time.time()
                    for rule in active_rules:
                        name = rule.name
                        aim_cd_ms = rule.aim_cooldown_ms
                        if aim_cd_ms > 0:
                            aim_cooldown_until[name] = _now + aim_cd_ms / 1000.0

                try:
                    with perf_stats.timer("inference_ms"):
                        result = inference_engine.predict(frame)
                except StopIteration:
                    for name in active_names:
                        settle[name] = 0
                        filtered_error[name] = None
                        raw_error_signs[name] = None
                        reversal_locks[name] = 0
                    post_shot_suppressor.reset()
                    self._set_overlay_state(False)
                    if perf_stats.enabled:
                        perf_stats.record_ms("end_to_end_ms", (time.perf_counter_ns() - frame_started_ns) / 1_000_000.0)
                    continue

                with perf_stats.timer("postprocess_ms"):
                    boxes = getattr(result, "boxes", None)
                    with perf_stats.timer("cpu_transfer_ms"):
                        extracted = extract_filtered_detections(
                            boxes=boxes,
                            target_class_ids=active_target_classes,
                            roi_left=capture_region.roi_left,
                            roi_top=capture_region.roi_top,
                        )
                    boxes_xyxy = extracted.boxes_xyxy
                    boxes_cls = extracted.boxes_cls
                    perf_stats.record_count("source_boxes_count", extracted.source_count)
                    perf_stats.record_count("selected_boxes_count", extracted.selected_count)

                overlay_set = False
                post_shot_target_seen = False
                post_shot_recoil_state = self._runtime_recoil_alignment_state() if post_shot_config.enabled else None
                post_shot_recoil_active = bool(post_shot_recoil_state is not None and post_shot_recoil_state.get("active", False))
                movement_candidates: list[dict[str, Any]] = []
                click_ready: list[dict[str, Any]] = []
                base_sens_mult_x = round((game_width / mon_width) / max(user_sens, 1e-6), 4)
                base_sens_mult_y = round((game_height / mon_height) / max(user_sens, 1e-6), 4)

                with perf_stats.timer("candidate_ms"):
                    for rule in active_rules:
                        name = rule.name
                        cfg = rule.raw
                        now = time.time()

                        target_classes = rule.target_classes(global_target_sides)
                        if not target_classes:
                            settle[name] = 0
                            filtered_error[name] = None
                            raw_error_signs[name] = None
                            reversal_locks[name] = 0
                            pos_smoother.reset(name)
                            continue

                        aim_strength = rule.aim_strength
                        sens_mult_x = round(base_sens_mult_x, 4)
                        sens_mult_y = round(base_sens_mult_y, 4)
                        snap_distance = rule.snap_distance
                        max_aim_speed_px = rule.max_aim_speed_px
                        curve_points = list(rule.curve_points)
                        aim_smoothing_alpha = rule.aim_smoothing_alpha
                        noise_amount = rule.noise_amount

                        aim_mode = rule.aim_mode
                        snap_r2 = rule.snap_radius_sq
                        auto_shoot = rule.auto_shoot
                        zone_width = rule.zone_width
                        zone_height = rule.zone_height
                        zone_y_pos = rule.zone_y_pos

                        left_button_held = activation.button_held("left")
                        spray_offset_x, spray_offset_y = self._spray_target_offset_for_rule(
                            cfg=cfg,
                            pattern_file=pattern_file,
                            recoil_sync=recoil_sync,
                            fallback_program_sens=user_sens,
                            left_button_held=left_button_held,
                        )
                        if not overlay_set and left_button_held and rule.spray_target_offset_enabled:
                            self._set_overlay_state(True, spray_offset_x, spray_offset_y, name)
                            overlay_set = True

                        best_movement = None
                        best_click = None
                        for box, cls in zip(boxes_xyxy, boxes_cls):
                            if int(cls) not in target_classes:
                                continue

                            x1, y1, x2, y2 = map(int, box[:4])
                            box_tuple = (x1, y1, x2, y2)
                            tx, ty = _aim_point_for_box(
                                box=box_tuple,
                                crosshair=(cx, cy),
                                aim_mode=aim_mode,
                                head_offset=rule.head_offset,
                                body_knee_offset=rule.body_knee_offset,
                            )
                            body_y_axis_loose = _body_y_axis_is_loose(
                                box=box_tuple,
                                crosshair=(cx, cy),
                                aim_mode=aim_mode,
                                body_knee_offset=rule.body_knee_offset,
                            )

                            pred_bullet_cx = cx - spray_offset_x
                            pred_bullet_cy = cy - spray_offset_y

                            target_dx_from_center = tx - cx
                            target_dy_from_center = ty - cy
                            pred_dx_from_center = pred_bullet_cx - cx
                            pred_dy_from_center = pred_bullet_cy - cy

                            err_x, err_y = _raw_aim_error(
                                target=(float(tx), float(ty)),
                                predicted_bullet=(float(pred_bullet_cx), float(pred_bullet_cy)),
                                body_y_axis_loose=body_y_axis_loose,
                            )

                            if (
                                pred_dx_from_center != 0
                                and target_dx_from_center * pred_dx_from_center > 0
                                and abs(target_dx_from_center) <= abs(pred_dx_from_center)
                            ):
                                err_x = 0.0

                            if (
                                pred_dy_from_center != 0
                                and target_dy_from_center * pred_dy_from_center > 0
                                and abs(target_dy_from_center) <= abs(pred_dy_from_center)
                            ):
                                err_y = 0.0

                            aim_d2 = (tx - cx) * (tx - cx) + (ty - cy) * (ty - cy)
                            if aim_d2 <= snap_r2 and (best_movement is None or aim_d2 < best_movement["d2"]):
                                best_movement = {
                                    "raw_err_x": float(err_x),
                                    "raw_err_y": float(err_y),
                                    "d2": float(aim_d2),
                                    "target_tx": float(tx),
                                    "target_ty": float(ty),
                                    "pred_bullet_cx": float(pred_bullet_cx),
                                    "pred_bullet_cy": float(pred_bullet_cy),
                                    "body_y_axis_loose": body_y_axis_loose,
                                }

                            if _auto_shoot_zone_contains_crosshair(
                                box=box_tuple,
                                crosshair=(cx, cy),
                                zone_width=zone_width,
                                zone_height=zone_height,
                                zone_y_pos=zone_y_pos,
                            ):
                                box_cx = (x1 + x2) >> 1
                                box_cy = (y1 + y2) >> 1
                                center_d2 = (box_cx - cx) * (box_cx - cx) + (box_cy - cy) * (box_cy - cy)
                                if best_click is None or center_d2 < best_click["d2"]:
                                    best_click = {
                                        "d2": float(center_d2),
                                    }

                        if best_movement is None and best_click is None:
                            settle[name] = 0
                            filtered_error[name] = None
                            per_rule_smooth.pop(name, None)
                            raw_error_signs[name] = None
                            reversal_locks[name] = 0
                            pos_smoother.reset(name)
                            continue

                        if best_movement is not None:
                            post_shot_target_seen = True
                            raw_tx = float(best_movement["target_tx"])
                            raw_ty = float(best_movement["target_ty"])
                            # Smooth raw detections to dampen YOLO bounding-box jitter
                            smooth_tx, smooth_ty = pos_smoother.smooth(name, raw_tx, raw_ty)

                            target_tx = smooth_tx
                            target_ty = smooth_ty
                            pred_bullet_cx = float(best_movement["pred_bullet_cx"])
                            pred_bullet_cy = float(best_movement["pred_bullet_cy"])

                            target_dx_from_center = target_tx - cx
                            target_dy_from_center = target_ty - cy
                            pred_dx_from_center = pred_bullet_cx - cx
                            pred_dy_from_center = pred_bullet_cy - cy

                            raw_dx, raw_dy = _raw_aim_error(
                                target=(target_tx, target_ty),
                                predicted_bullet=(pred_bullet_cx, pred_bullet_cy),
                                body_y_axis_loose=bool(best_movement["body_y_axis_loose"]),
                            )

                            if (
                                pred_dx_from_center != 0
                                and target_dx_from_center * pred_dx_from_center > 0
                                and abs(target_dx_from_center) <= abs(pred_dx_from_center)
                            ):
                                raw_dx = 0.0

                            if (
                                pred_dy_from_center != 0
                                and target_dy_from_center * pred_dy_from_center > 0
                                and abs(target_dy_from_center) <= abs(pred_dy_from_center)
                            ):
                                raw_dy = 0.0

                            dist = (raw_dx * raw_dx + raw_dy * raw_dy) ** 0.5
                            limit_dx = float(best_movement["raw_err_x"])
                            limit_dy = float(best_movement["raw_err_y"])
                            limit_dist = (limit_dx * limit_dx + limit_dy * limit_dy) ** 0.5
                            raw_sign = _raw_error_sign((limit_dx, limit_dy), jitter_deadzone_px)
                            new_lock = _anti_oscillation_reversal_lock_frames(
                                previous_sign=raw_error_signs.get(name),
                                current_sign=raw_sign,
                                distance_px=limit_dist,
                                radius_px=anti_oscillation_radius_px,
                                lock_frames=anti_oscillation_lock_frames,
                            )
                            if new_lock > 0:
                                reversal_locks[name] = new_lock
                            raw_error_signs[name] = raw_sign

                            if reversal_locks.get(name, 0) > 0:
                                reversal_locks[name] = max(0, reversal_locks[name] - 1)
                                filtered_error[name] = None
                                per_rule_smooth.pop(name, None)
                                continue

                            prev = filtered_error.get(name)
                            if prev is None or dist >= near_smoothing_radius_px:
                                filt_dx = raw_dx
                                filt_dy = raw_dy
                            else:
                                adaptive_alpha = max(near_smoothing_alpha, min(1.0, dist / max(1.0, near_smoothing_radius_px)))
                                filt_dx = prev[0] + adaptive_alpha * (raw_dx - prev[0])
                                filt_dy = prev[1] + adaptive_alpha * (raw_dy - prev[1])

                            if abs(filt_dx) <= jitter_deadzone_px:
                                filt_dx = 0.0
                            if abs(filt_dy) <= jitter_deadzone_px:
                                filt_dy = 0.0
                            filt_dx, filt_dy = _lock_body_y_axis(
                                (filt_dx, filt_dy),
                                body_y_axis_loose=bool(best_movement["body_y_axis_loose"]),
                            )

                            post_shot_x_limit: float | None = None
                            post_shot_y_limit: float | None = None
                            if post_shot_config.enabled and filt_dx != 0.0:
                                suppressed_filt_dx = post_shot_suppressor.apply_x(
                                    filt_dx,
                                    now=time.perf_counter(),
                                )
                                if suppressed_filt_dx != filt_dx:
                                    post_shot_x_limit = suppressed_filt_dx
                                    filt_dx = suppressed_filt_dx
                            if post_shot_config.enabled and filt_dy > 0.0:
                                suppressed_filt_dy = post_shot_suppressor.apply_y(
                                    filt_dy,
                                    now=time.perf_counter(),
                                    recoil_active=post_shot_recoil_active,
                                )
                                if suppressed_filt_dy < filt_dy:
                                    post_shot_y_limit = suppressed_filt_dy
                                    filt_dy = suppressed_filt_dy

                            filtered_error[name] = (filt_dx, filt_dy)
                            if now >= aim_cooldown_until.get(name, 0.0):
                                movement_candidates.append({
                                    "name": name,
                                    "cfg": cfg,
                                    "sens_mult_x": sens_mult_x,
                                    "sens_mult_y": sens_mult_y,
                                    "dx": float(filt_dx),
                                    "dy": float(filt_dy),
                                    "limit_dx": limit_dx,
                                    "limit_dy": limit_dy,
                                    "d2": best_movement["d2"],
                                    "now": now,
                                    "aim_strength": aim_strength,
                                    "snap_distance": snap_distance,
                                    "max_aim_speed_px": max_aim_speed_px,
                                    "curve_points": curve_points,
                                    "aim_smoothing_alpha": aim_smoothing_alpha,
                                    "noise_amount": noise_amount,
                                    "anti_oscillation_radius_px": anti_oscillation_radius_px,
                                    "anti_oscillation_reserve_counts": anti_oscillation_reserve_counts,
                                    "body_y_axis_loose": best_movement["body_y_axis_loose"],
                                    "post_shot_x_limit": post_shot_x_limit,
                                    "post_shot_y_limit": post_shot_y_limit,
                                })
                        else:
                            filtered_error[name] = None
                            per_rule_smooth.pop(name, None)
                            raw_error_signs[name] = None
                            reversal_locks[name] = 0
                            pos_smoother.reset(name)

                        if best_click is not None:
                            threshold = rule.settle_frames
                            settle[name] = min(threshold, settle[name] + 1)
                            if settle[name] >= threshold and auto_shoot and not _shot_cooldown_active(now=now, cooldown_until=cooldown_until[name]):
                                click_ready.append({
                                    "name": name,
                                    "cfg": cfg,
                                    "d2": best_click["d2"],
                                    "now": now,
                                    "hold_ms": rule.click_hold_ms,
                                })
                            elif settle[name] >= threshold:
                                settle[name] = threshold
                        else:
                            settle[name] = 0

                if not overlay_set:
                    self._set_overlay_state(False)

                if post_shot_config.enabled:
                    if post_shot_target_seen:
                        post_shot_suppressor.note_target_visible()
                    else:
                        post_shot_suppressor.note_target_missing(time.perf_counter())

                if not movement_candidates and not click_ready:
                    if perf_stats.enabled:
                        perf_stats.record_ms("end_to_end_ms", (time.perf_counter_ns() - frame_started_ns) / 1_000_000.0)
                    continue

                if movement_candidates:
                    with perf_stats.timer("motion_ms"):
                        motions: list[aim_motion.AimMotionResult] = []
                        for m in movement_candidates:
                            error_px = _smoothed_error_for_rule(
                                rule_name=m["name"],
                                error_px=(m["dx"], m["dy"]),
                                smoothing_alpha=m["aim_smoothing_alpha"],
                                per_rule_smooth=per_rule_smooth,
                            )
                            post_shot_x_limit = m.get("post_shot_x_limit")
                            post_shot_y_limit = m.get("post_shot_y_limit")
                            if isinstance(post_shot_x_limit, float):
                                error_px = (
                                    clamp_x_to_limit(error_px[0], post_shot_x_limit),
                                    error_px[1],
                                )
                                per_rule_smooth[m["name"]] = error_px
                            if isinstance(post_shot_y_limit, float):
                                error_px = (
                                    error_px[0],
                                    clamp_positive_y_to_limit(error_px[1], post_shot_y_limit),
                                )
                                per_rule_smooth[m["name"]] = error_px
                            error_px = _lock_body_y_axis(error_px, body_y_axis_loose=bool(m["body_y_axis_loose"]))
                            if m["body_y_axis_loose"]:
                                per_rule_smooth[m["name"]] = error_px
                            motion = aim_motion.compute_aim_motion(
                                error_px,
                                aim_motion.AimMotionConfig(
                                    aim_strength=m["aim_strength"],
                                    snap_distance=m["snap_distance"],
                                    max_aim_speed_px=m["max_aim_speed_px"],
                                    sens_mult_x=m["sens_mult_x"],
                                    sens_mult_y=m["sens_mult_y"],
                                    noise_px=m["noise_amount"],
                                    curve_points=m["curve_points"],
                                    anti_oscillation_radius_px=m["anti_oscillation_radius_px"],
                                    anti_oscillation_reserve_counts=m["anti_oscillation_reserve_counts"],
                                ),
                                limit_error_px=(m["limit_dx"], m["limit_dy"]),
                            )
                            motions.append(motion)
                            if motion.arrived:
                                per_rule_smooth.pop(m["name"], None)
                                filtered_error[m["name"]] = None
                                raw_error_signs[m["name"]] = None
                                reversal_locks[m["name"]] = 0
                                pos_smoother.reset(m["name"])
                    mdx, mdy = _sum_motion_counts(motions)
                    if mdx or mdy:
                        with perf_stats.timer("input_emit_ms"):
                            vmouse.emit_rel(mdx, mdy)

                if click_ready:
                    best_click = min(click_ready, key=lambda item: item["d2"])
                    hold_ms = int(best_click["hold_ms"])
                    with perf_stats.timer("input_emit_ms"):
                        self._note_post_shot_cv_auto_candidate()
                        if not input_worker.enqueue_click(hold_ms):
                            vmouse.click_once(hold_ms)
                    triggered_names = {item["name"] for item in click_ready}
                    for triggered_name in triggered_names:
                        base_cooldown = float(compiled_rules[triggered_name].cooldown_ms) / 1000.0
                        cooldown_until[triggered_name] = best_click["now"] + base_cooldown
                        settle[triggered_name] = 0
                if perf_stats.enabled:
                    perf_stats.record_ms("end_to_end_ms", (time.perf_counter_ns() - frame_started_ns) / 1_000_000.0)

        except Exception as exc:
            self.status(str(exc), "error")
        finally:
            self._set_overlay_state(False)
            if perf_stats.enabled:
                elapsed = max(time.perf_counter() - run_started, 1e-9)
                perf_stats.record_count("capture_skipped_or_backpressured", grab.buffer.backpressure_count)
                payload = perf_stats.summary(
                    extra={
                        "capture_fps": frames_processed / elapsed,
                        "frame_count": frames_processed,
                        "capture_region": capture_region.as_capture_dict(),
                    },
                )
                if perf_output_path:
                    Path(perf_output_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(perf_output_path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            if scope_capture is not None:
                scope_capture.close()
            grab.stop()
            grab.join(timeout=1.0)
            input_worker.stop(timeout=1.0)
            _safe_stop_listener(key_listener)
            _safe_stop_listener(mouse_listener)
            self._thread = None
            self.status("Stopped.")
