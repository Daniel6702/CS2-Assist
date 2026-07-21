from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import aim_motion
from .activation import canonical_weapon_name
from .curve_config import build_curve_library
from .patterns import _CLASS_INDEX_BY_SIDE_AND_TYPE, _truthy


def _rule_priority(rule: dict[str, Any]) -> int:
    try:
        return int(rule.get("priority", 0))
    except (TypeError, ValueError):
        return 0


def _curve_points_for_rule(aim_curves: dict[str, Any], curve_id: str) -> tuple[aim_motion.CurvePoint, ...]:
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
        return tuple((float(point[0]), float(point[1])) for point in linear)
    return tuple(sorted(points, key=lambda item: item[0]))


def _allowed_weapons(rule: dict[str, Any]) -> frozenset[str] | None:
    restrictions = rule.get("allowed_weapons", rule.get("only_when_weapon"))
    if restrictions in (None, "", []):
        return None
    if isinstance(restrictions, str):
        wanted = [restrictions]
    elif isinstance(restrictions, (list, tuple, set)):
        wanted = [str(item) for item in restrictions if str(item).strip()]
    else:
        wanted = [str(restrictions)]
    return frozenset(canonical_weapon_name(item) for item in wanted)


def _target_types(rule: dict[str, Any]) -> tuple[str, ...]:
    target_type = str(rule.get("target_type", "both") or "both").strip().lower()
    if target_type in {"type1", "body", "tc"}:
        return ("type1",)
    if target_type in {"type2", "head", "thch"}:
        return ("type2",)
    return ("type1", "type2")


@dataclass(frozen=True, slots=True)
class CompiledRule:
    name: str
    raw: dict[str, Any]
    priority: int
    activation: dict[str, Any]
    allowed_weapons: frozenset[str] | None
    target_types: tuple[str, ...]
    requires_scope: bool
    auto_shoot: bool
    spray_target_offset_enabled: bool
    aim_mode: str
    head_offset: float
    body_knee_offset: float
    snap_distance: int
    snap_radius_sq: int
    settle_frames: int
    click_hold_ms: int
    cooldown_ms: float
    aim_cooldown_ms: float
    aim_strength: float
    max_aim_speed_px: int
    curve_points: tuple[aim_motion.CurvePoint, ...]
    aim_smoothing_alpha: float
    noise_amount: float
    zone_width: int
    zone_height: int
    zone_y_pos: float

    def weapon_allowed(self, current_weapon: str | None) -> bool:
        if self.allowed_weapons is None:
            return True
        if not current_weapon:
            return False
        return canonical_weapon_name(current_weapon) in self.allowed_weapons

    def scope_allowed(self, scoped_visual: bool) -> bool:
        return bool(scoped_visual) if self.requires_scope else True

    def target_classes(self, global_target_sides: set[str]) -> set[int]:
        if not global_target_sides:
            return set()
        classes: set[int] = set()
        for side in global_target_sides:
            mapping = _CLASS_INDEX_BY_SIDE_AND_TYPE.get(side, {})
            for type_name in self.target_types:
                class_idx = mapping.get(type_name)
                if class_idx is not None:
                    classes.add(class_idx)
        return classes


def compile_rule(name: str, rule: dict[str, Any], aim_curves: dict[str, Any]) -> CompiledRule:
    snap_distance = int(rule.get("SNAP_DISTANCE", 200))
    requirement = rule.get("only_when_scoped_visual", rule.get("only_when_scoped", False))
    return CompiledRule(
        name=name,
        raw=rule,
        priority=_rule_priority(rule),
        activation=dict(rule.get("activation", {"device": "keyboard", "key": "alt"})),
        allowed_weapons=_allowed_weapons(rule),
        target_types=_target_types(rule),
        requires_scope=_truthy(requirement),
        auto_shoot=_truthy(rule.get("auto_shoot", True)),
        spray_target_offset_enabled=_truthy(rule.get("spray_target_offset_enabled", False)),
        aim_mode=str(rule["AIM_MODE"]).lower(),
        head_offset=float(rule["HEAD_OFFSET"]),
        body_knee_offset=float(rule.get("BODY_KNEE_OFFSET", 0.50)),
        snap_distance=snap_distance,
        snap_radius_sq=snap_distance * snap_distance,
        settle_frames=max(1, int(rule["SETTLE_FRAMES"])),
        click_hold_ms=int(rule["CLICK_HOLD_MS"]),
        cooldown_ms=float(rule["COOLDOWN_MS"]),
        aim_cooldown_ms=float(rule.get("auto_shoot_aim_cooldown_ms", 0)),
        aim_strength=float(rule.get("AIM_STRENGTH", 0.5)),
        max_aim_speed_px=int(rule.get("MAX_AIM_SPEED_PX", 50)),
        curve_points=_curve_points_for_rule(aim_curves, str(rule.get("AIM_CURVE_ID", "linear"))),
        aim_smoothing_alpha=float(rule.get("SMOOTHING_ALPHA", 0.0)),
        noise_amount=float(rule.get("NOISE_AMOUNT", 0.0)),
        zone_width=int(rule.get("AUTO_SHOOT_ZONE_WIDTH", 28)),
        zone_height=int(rule.get("AUTO_SHOOT_ZONE_HEIGHT", 36)),
        zone_y_pos=float(rule.get("AUTO_SHOOT_ZONE_Y_POS", 0.35)),
    )


def compile_rules(configs: dict[str, dict[str, Any]], aim_curves: dict[str, Any]) -> dict[str, CompiledRule]:
    return {name: compile_rule(name, rule, aim_curves) for name, rule in configs.items()}


def highest_priority_rules(rules: list[CompiledRule]) -> list[CompiledRule]:
    if not rules:
        return []
    highest = max(rule.priority for rule in rules)
    return [rule for rule in rules if rule.priority == highest]
