from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .weapon_recoil import PostShotTimingConfig


PostShotConfigValue = bool | int | float


@dataclass(frozen=True, slots=True)
class PostShotSuppressionConfig(PostShotTimingConfig):
    enabled: bool = True
    stabilization_strength: float = 1.0
    horizontal_stabilization_strength: float = 0.5
    manual_release_max_hold_ms: int = 300
    candidate_validation_window_ms: int = 300
    isolated_gap_ms: int = 260
    sustained_shot_index: int = 2
    recoil_active_downward_scale: float = 0.05
    reset_on_target_loss: bool = True
    target_loss_grace_ms: int = 50
    max_frame_age_ms: int = 120


def default_post_shot_y_suppression_config(*, enabled: bool = False) -> dict[str, PostShotConfigValue]:
    config = PostShotSuppressionConfig(enabled=enabled)
    return {
        "enabled": config.enabled,
        "stabilization_strength": config.stabilization_strength,
        "horizontal_stabilization_strength": config.horizontal_stabilization_strength,
        "manual_release_max_hold_ms": config.manual_release_max_hold_ms,
    }


def post_shot_config_from_mapping(raw: dict[str, Any] | None) -> PostShotSuppressionConfig:
    values = asdict(PostShotSuppressionConfig(enabled=False))
    if raw is not None:
        _apply_raw_config(values, raw)
    _apply_simple_controls(values)
    return PostShotSuppressionConfig(**values)


def _apply_raw_config(values: dict[str, PostShotConfigValue], raw: dict[str, Any]) -> None:
    for key, default in values.items():
        if key not in raw:
            continue
        values[key] = _coerce_config_value(raw[key], default)
    if "downward_reduction" not in raw and "min_downward_scale" in raw:
        values["stabilization_strength"] = (1.0 - _coerce_float(raw["min_downward_scale"], 0.02)) / 0.98
    if "stabilization_strength" not in raw and "downward_reduction" in raw:
        values["stabilization_strength"] = _coerce_float(raw["downward_reduction"], 0.98) / 0.98


def _apply_simple_controls(values: dict[str, PostShotConfigValue]) -> None:
    values["stabilization_strength"] = max(0.0, float(values["stabilization_strength"]))
    values["horizontal_stabilization_strength"] = max(0.0, float(values["horizontal_stabilization_strength"]))
    values["manual_release_max_hold_ms"] = max(0, int(values["manual_release_max_hold_ms"]))


def _coerce_config_value(value: Any, default: PostShotConfigValue) -> PostShotConfigValue:
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, int):
        return _coerce_int(value, default)
    return _coerce_float(value, default)


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
