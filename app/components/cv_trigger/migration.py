from __future__ import annotations

from typing import Any

from .curve_config import LEGACY_CURVE_MAP, PRESET_CURVES, build_curve_library, legacy_response_curve_to_id
from .patterns import _infer_target_type_from_legacy_classes, _truthy

_PRESET_CURVES = PRESET_CURVES
_LEGACY_CURVE_MAP = LEGACY_CURVE_MAP

_LEGACY_RULE_KEYS = {
    "RESPONSE_CURVE",
    "CURVE_INTENSITY",
    "CONSTANT_SPEED_PX",
    "ACCEL_BOOST",
    "ANTI_OVERSHOOT",
    "SENS_COEFF",
}


def _to_scalar_aim_strength(value: float, legacy_percent: bool = True) -> float:
    if legacy_percent and value > 1.0:
        return value / 100.0
    return value


def _build_curve_library() -> dict[str, dict[str, Any]]:
    return build_curve_library()


def _migrate_rule(item: dict[str, Any], raw_item: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize a single CV trigger rule to canonical format.
    
    Accepts legacy/transitional keys, outputs canonical shape with
    scalar AIM_STRENGTH, AIM_CURVE_ID, MAX_AIM_SPEED_PX, etc.
    Old runtime keys (RESPONSE_CURVE, CURVE_INTENSITY, CONSTANT_SPEED_PX,
    ACCEL_BOOST, ANTI_OVERSHOOT) are consumed and removed.
    """
    item = dict(item)

    src = raw_item or item
    canonical_shape = "AIM_CURVE_ID" in item or "MAX_AIM_SPEED_PX" in item
    legacy_percent = (not canonical_shape) or bool(_LEGACY_RULE_KEYS & set(item)) or bool(_LEGACY_RULE_KEYS & set(src))
    old_sens = src.get("SENS_COEFF")
    if old_sens is not None and "AIM_STRENGTH" not in item:
        item["AIM_STRENGTH"] = min(float(old_sens) * 50.0, 100.0)
        legacy_percent = True
    item.pop("SENS_COEFF", None)

    raw_str = item.pop("AIM_STRENGTH", None)
    if raw_str is not None:
        try:
            item["AIM_STRENGTH"] = _to_scalar_aim_strength(float(raw_str), legacy_percent=legacy_percent)
        except (ValueError, TypeError):
            item["AIM_STRENGTH"] = 0.5
    else:
        item["AIM_STRENGTH"] = 0.5

    legacy_curve = item.pop("RESPONSE_CURVE", None)
    if legacy_curve is not None:
        curve_id = legacy_response_curve_to_id(legacy_curve)
    else:
        curve_id = item.pop("AIM_CURVE_ID", "linear")
    item.pop("CURVE_INTENSITY", None)
    item["AIM_CURVE_ID"] = curve_id

    old_speed = item.pop("CONSTANT_SPEED_PX", None)
    if old_speed is not None:
        item.setdefault("MAX_AIM_SPEED_PX", int(old_speed))
    item.setdefault("MAX_AIM_SPEED_PX", 50)

    item.pop("ACCEL_BOOST", None)
    item.pop("ANTI_OVERSHOOT", None)

    item.setdefault("SNAP_DISTANCE", 200)
    item.setdefault("SMOOTHING_ALPHA", 0.0)
    item.setdefault("NOISE_AMOUNT", 0.0)

    return item


def _migrate_legacy_config(config: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(config)
    if "aim_curves" not in migrated:
        migrated["aim_curves"] = _build_curve_library()

    if isinstance(config.get("configs"), dict):
        out_configs: dict[str, Any] = {}
        min_conf = None
        max_img = None
        for name, raw_item in dict(migrated.get("configs", {})).items():
            item = dict(raw_item or {})
            legacy_classes = item.pop("CLASSES", item.get("CLASSES", None))
            item.pop("CONFIDENCE", None)
            item.pop("IMG_SIZE", None)

            activation = item.get("activation")
            if not isinstance(activation, dict):
                activation = {"device": "keyboard", "key": "alt"}
            item["activation"] = activation

            item["enabled"] = _truthy(item.get("enabled", True))
            item["auto_shoot"] = _truthy(item.get("auto_shoot", True))
            item["spray_target_offset_enabled"] = _truthy(item.get("spray_target_offset_enabled", False))
            item["only_when_scoped_visual"] = _truthy(
                item.get("only_when_scoped_visual", item.get("only_when_scoped", False))
            )
            item["target_type"] = str(item.get("target_type") or _infer_target_type_from_legacy_classes(legacy_classes)).strip().lower() or "both"

            item = _migrate_rule(item, raw_item)

            if "allowed_weapons" not in item and "only_when_weapon" in item:
                item["allowed_weapons"] = item.get("only_when_weapon")

            try:
                conf = float(raw_item.get("CONFIDENCE", 0.15))
            except Exception:
                conf = 0.15
            try:
                img = int(raw_item.get("IMG_SIZE", 384))
            except Exception:
                img = 384
            min_conf = conf if min_conf is None else min(min_conf, conf)
            max_img = img if max_img is None else max(max_img, img)
            out_configs[str(name)] = item

        migrated["configs"] = out_configs
        migrated.setdefault("inference_confidence", min_conf if min_conf is not None else 0.15)
        migrated.setdefault("inference_img_size", max_img if max_img is not None else 384)
        migrated.setdefault("use_gsi_opponent_side", False)
        migrated.setdefault("manual_target_side", "both")
        return migrated

    profiles = dict(config.get("profiles", {}))
    active_profile = str(config.get("active_profile", "pistol"))
    hold_mode = str(config.get("hold_mode", "alt")).strip().lower() or "alt"
    legacy_profile: dict[str, Any] = dict(profiles.get(active_profile, {}))
    if not legacy_profile:
        legacy_profile = {
            "AIM_MODE": "head",
            "HEAD_OFFSET": 0.12,
            "SNAP_DISTANCE": 200,
            "SETTLE_FRAMES": 2,
            "CLICK_HOLD_MS": 15,
            "COOLDOWN_MS": 250,
            "AIM_STRENGTH": 60.0,
            "RESPONSE_CURVE": "proportional",
            "CURVE_INTENSITY": 1.0,
            "CONSTANT_SPEED_PX": 50,
            "ACCEL_BOOST": 1.0,
            "ANTI_OVERSHOOT": True,
            "SMOOTHING_ALPHA": 0.0,
            "NOISE_AMOUNT": 0.0,
            "CROSS_X_THRESH": 14,
            "CROSS_Y_THRESH_TOP": 18,
            "CROSS_Y_THRESH_BOT": 32,
        }

    # migrate SENS_COEFF -> AIM_STRENGTH in legacy profile
    if "SENS_COEFF" in legacy_profile and "AIM_STRENGTH" not in legacy_profile:
        legacy_profile["AIM_STRENGTH"] = min(float(legacy_profile["SENS_COEFF"]) * 50.0, 100.0)
    legacy_profile.pop("SENS_COEFF", None)

    legacy_classes = legacy_profile.pop("CLASSES", legacy_profile.get("CLASSES", None))
    legacy_profile.setdefault("enabled", True)
    legacy_profile.setdefault("activation", {"device": "keyboard", "key": hold_mode})
    legacy_profile.setdefault("auto_shoot", True)
    legacy_profile.setdefault("spray_target_offset_enabled", False)
    legacy_profile.setdefault("only_when_scoped_visual", False)
    legacy_profile.setdefault("target_type", _infer_target_type_from_legacy_classes(legacy_classes))

    legacy_profile = _migrate_rule(legacy_profile)

    legacy_profile.pop("CONFIDENCE", None)
    legacy_profile.pop("IMG_SIZE", None)

    migrated["configs"] = {active_profile: legacy_profile}
    migrated.setdefault("inference_confidence", float(config.get("CONFIDENCE", 0.15) or 0.15))
    migrated.setdefault("inference_img_size", int(config.get("IMG_SIZE", 384) or 384))
    migrated.setdefault("use_gsi_opponent_side", False)
    migrated.setdefault("manual_target_side", "both")
    return migrated
