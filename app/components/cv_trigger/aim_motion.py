from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable

CurvePoint = tuple[float, float]


@dataclass(frozen=True)
class AimMotionConfig:
    aim_strength: float
    snap_distance: int
    max_aim_speed_px: int
    sens_mult_x: float
    sens_mult_y: float
    noise_px: float
    curve_points: list[CurvePoint]
    anti_oscillation_radius_px: float = 0.0
    anti_oscillation_reserve_counts: int = 0


@dataclass(frozen=True)
class AimMotionResult:
    dx: int
    dy: int
    arrived: bool


def interpolate_curve(points: list[CurvePoint], x: float) -> float:
    """Linearly interpolate curve y at normalized x, clamping x to [0, 1]."""
    if not points:
        return 0.0
    if x <= 0.0:
        return points[0][1]
    if x >= 1.0:
        return points[-1][1]
    lo, hi = 0, len(points) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if points[mid][0] <= x:
            lo = mid
        else:
            hi = mid
    x0, y0 = points[lo]
    x1, y1 = points[hi]
    if x1 == x0:
        return y0
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def compute_aim_motion(
    error_px: tuple[float, float],
    config: AimMotionConfig,
    noise_rng: Callable[[float, float], float] | None = None,
    limit_error_px: tuple[float, float] | None = None,
) -> AimMotionResult:
    ex, ey = error_px
    distance = math.hypot(ex, ey)

    if distance == 0.0:
        return AimMotionResult(dx=0, dy=0, arrived=True)
    if config.aim_strength == 0.0:
        return AimMotionResult(dx=0, dy=0, arrived=False)
    if config.snap_distance <= 0:
        return AimMotionResult(dx=0, dy=0, arrived=False)

    norm_dist = distance / config.snap_distance
    if norm_dist > 1.0:
        return AimMotionResult(dx=0, dy=0, arrived=False)

    curve_y = interpolate_curve(config.curve_points, norm_dist)
    speed_px = config.max_aim_speed_px * config.aim_strength * curve_y

    dx_norm = ex / distance
    dy_norm = ey / distance

    raw_x = speed_px * dx_norm
    raw_y = speed_px * dy_norm

    # Convert to mouse counts with sensitivity scaling
    mouse_x = raw_x * config.sens_mult_x
    mouse_y = raw_y * config.sens_mult_y

    dx_raw = int(round(mouse_x))
    dy_raw = int(round(mouse_y))

    # Bounded noise injection before final clamp
    if config.noise_px > 0:
        rng = noise_rng if noise_rng is not None else random.uniform
        noise_x = rng(-config.noise_px, config.noise_px)
        noise_y = rng(-config.noise_px, config.noise_px)
        dx_raw += int(round(noise_x * config.sens_mult_x))
        dy_raw += int(round(noise_y * config.sens_mult_y))

    safety_error = limit_error_px if limit_error_px is not None else error_px
    reserve_counts = _reserve_counts_for_error(safety_error, config)
    dx = _clamp_axis_to_error(dx_raw, safety_error[0], config.sens_mult_x, reserve_counts)
    dy = _clamp_axis_to_error(dy_raw, safety_error[1], config.sens_mult_y, reserve_counts)

    arrived = _safe_count_limit(safety_error[0], config.sens_mult_x, reserve_counts) == 0 and _safe_count_limit(safety_error[1], config.sens_mult_y, reserve_counts) == 0
    return AimMotionResult(dx=dx, dy=dy, arrived=arrived)


def _reserve_counts_for_error(error_px: tuple[float, float], config: AimMotionConfig) -> int:
    if config.anti_oscillation_radius_px <= 0.0:
        return 0
    if math.hypot(error_px[0], error_px[1]) > config.anti_oscillation_radius_px:
        return 0
    return max(0, config.anti_oscillation_reserve_counts)


def _safe_count_limit(error_px: float, sens_mult: float, reserve_counts: int = 0) -> int:
    raw_limit = int(math.floor(abs(error_px * sens_mult) + 1e-9))
    return max(0, raw_limit - reserve_counts)


def _clamp_axis_to_error(proposed: int, error_px: float, sens_mult: float, reserve_counts: int = 0) -> int:
    safe = _safe_count_limit(error_px, sens_mult, reserve_counts)
    if safe <= 0 or proposed == 0 or error_px == 0.0:
        return 0
    target_sign = 1 if error_px > 0.0 else -1
    if proposed * target_sign <= 0:
        return 0
    return target_sign * min(abs(proposed), safe)
