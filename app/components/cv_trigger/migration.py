from __future__ import annotations

from typing import Any

from .patterns import _infer_target_type_from_legacy_classes, _truthy


def _migrate_legacy_config(config: dict[str, Any]) -> dict[str, Any]:
    if isinstance(config.get("configs"), dict):
        migrated = dict(config)
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
            "SNAP_DISTANCE": 50,
            "SETTLE_FRAMES": 2,
            "CLICK_HOLD_MS": 15,
            "COOLDOWN_MS": 250,
            "SENS_COEFF": 1.2,
            "CROSS_X_THRESH": 14,
            "CROSS_Y_THRESH_TOP": 18,
            "CROSS_Y_THRESH_BOT": 32,
        }

    legacy_classes = legacy_profile.pop("CLASSES", legacy_profile.get("CLASSES", None))
    legacy_profile.setdefault("enabled", True)
    legacy_profile.setdefault("activation", {"device": "keyboard", "key": hold_mode})
    legacy_profile.setdefault("auto_shoot", True)
    legacy_profile.setdefault("spray_target_offset_enabled", False)
    legacy_profile.setdefault("only_when_scoped_visual", False)
    legacy_profile.setdefault("target_type", _infer_target_type_from_legacy_classes(legacy_classes))
    legacy_profile.pop("CONFIDENCE", None)
    legacy_profile.pop("IMG_SIZE", None)

    migrated = dict(config)
    migrated["configs"] = {active_profile: legacy_profile}
    migrated.setdefault("inference_confidence", float(config.get("CONFIDENCE", 0.15) or 0.15))
    migrated.setdefault("inference_img_size", int(config.get("IMG_SIZE", 384) or 384))
    migrated.setdefault("use_gsi_opponent_side", False)
    migrated.setdefault("manual_target_side", "both")
    return migrated
