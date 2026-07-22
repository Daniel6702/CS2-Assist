from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .activation import _canon_text


PATTERNS_FILE = Path(__file__).resolve().parents[3] / "resources" / "mouse_patterns.json"

_PATTERN_ALIASES = {
    "ak": "weapon_ak47",
    "ak47": "weapon_ak47",
    "weaponak47": "weapon_ak47",
    "m4a1": "weapon_m4a1_silencer",
    "m4a1s": "weapon_m4a1_silencer",
    "m4a1silencer": "weapon_m4a1_silencer",
    "weaponm4a1silencer": "weapon_m4a1_silencer",
    "m4a4": "weapon_m4a1",
    "weaponm4a1": "weapon_m4a1",
    "famas": "weapon_famas",
    "weaponfamas": "weapon_famas",
    "galil": "weapon_galilar",
    "galilar": "weapon_galilar",
    "weapongalilar": "weapon_galilar",
    "ump": "weapon_ump45",
    "ump45": "weapon_ump45",
    "weaponump45": "weapon_ump45",
    "aug": "weapon_aug",
    "weaponaug": "weapon_aug",
    "sg": "weapon_sg556",
    "sg553": "weapon_sg556",
    "sg556": "weapon_sg556",
    "weaponsg556": "weapon_sg556",
}

def load_pattern_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"patterns": {}}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _pattern_index(pattern_file: dict[str, Any]) -> dict[str, str]:
    data = pattern_file.get("patterns", {})
    return {_canon_text(actual_name): actual_name for actual_name in data}


def resolve_pattern_name(pattern_file: dict[str, Any], requested_name: str | None) -> str | None:
    if not requested_name:
        return None

    data = pattern_file.get("patterns", {})
    if requested_name in data:
        return requested_name

    index = _pattern_index(pattern_file)
    canon = _canon_text(requested_name)

    direct = index.get(canon)
    if direct is not None:
        return direct

    alias_target = _PATTERN_ALIASES.get(canon)
    if alias_target is not None:
        if alias_target in data:
            return alias_target
        alias_direct = index.get(_canon_text(alias_target))
        if alias_direct is not None:
            return alias_direct

    return None


def _scaled_recoil_pattern_steps(pattern_file: dict[str, Any], requested_name: str | None, recoil_sync: dict[str, Any], fallback_program_sens: float) -> list[tuple[float, float, int]]:
    resolved_name = resolve_pattern_name(pattern_file, requested_name)
    if resolved_name is None:
        return []

    data = pattern_file.get("patterns", {})
    pattern_data = data.get(resolved_name, {})
    pattern_scale_x = float(pattern_data.get("scale_x", 1.0))
    pattern_scale_y = float(pattern_data.get("scale_y", 1.0))
    raw_steps = list(pattern_data.get("steps", []))
    axis = dict(recoil_sync.get("axis_strength_percent", {}) or {})
    sens = dict(recoil_sync.get("sensitivity", {}) or {})
    sens_ax = dict(sens.get("apply_to_axis", {}) or {})

    x_strength = float(axis.get("x", 100.0)) / 100.0
    y_strength = float(axis.get("y", 100.0)) / 100.0

    program_sens = float(sens.get("program_sens", fallback_program_sens) or fallback_program_sens or 1.0)
    reference_sens = float(sens.get("reference_sens", 2.52))
    sensitivity_enabled = bool(sens.get("enabled", True))
    modifier = 1.0
    if sensitivity_enabled and program_sens:
        modifier = reference_sens / program_sens

    mod_x = modifier if bool(sens_ax.get("x", True)) else 1.0
    mod_y = modifier if bool(sens_ax.get("y", True)) else 1.0

    out: list[tuple[float, float, int]] = []
    for step in raw_steps:
        try:
            dx = float(step.get("dx", 0.0)) * pattern_scale_x * x_strength * mod_x
            dy = float(step.get("dy", 0.0)) * pattern_scale_y * y_strength * mod_y
            duration_ms = max(1, int(step.get("duration_ms", 1)))
        except (AttributeError, TypeError, ValueError):
            continue
        out.append((dx, dy, duration_ms))
    return out


_load_pattern_file = load_pattern_file
_resolve_pattern_name = resolve_pattern_name


_CLASS_INDEX_BY_SIDE_AND_TYPE = {
    "t": {"type1": 2, "type2": 3},
    "ct": {"type1": 0, "type2": 1},
}


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"", "0", "false", "no", "off", "none", "null"}:
            return False
        if text in {"1", "true", "yes", "on"}:
            return True
    return bool(value)


def _normalize_side_name(value: Any) -> str | None:
    text = _canon_text(str(value) if value is not None else "")
    if text in {"t", "terrorist", "terrorists", "teamt"}:
        return "t"
    if text in {
        "ct",
        "counterterrorist",
        "counterterrorists",
        "counterterorist",
        "counterterorists",
        "counter",
        "teamct",
        "counterstrike",
    }:
        return "ct"
    return None


def _extract_player_side_from_payload(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None

    player = payload.get("player", {}) or {}
    map_info = payload.get("map", {}) or {}
    provider = payload.get("provider", {}) or {}

    candidates = [
        player.get("team"),
        player.get("team_name"),
        player.get("side"),
        provider.get("team"),
        provider.get("team_name"),
        map_info.get("team"),
        map_info.get("team_name"),
    ]
    for value in candidates:
        side = _normalize_side_name(value)
        if side is not None:
            return side
    return None


def _infer_target_type_from_legacy_classes(classes_value: Any) -> str:
    if classes_value in (None, "", []):
        return "both"
    try:
        values = {int(v) for v in classes_value}
    except (TypeError, ValueError):
        return "both"

    type1 = {0, 2}
    type2 = {1, 3}
    has_type1 = bool(values & type1)
    has_type2 = bool(values & type2)
    if has_type1 and has_type2:
        return "both"
    if has_type2:
        return "type2"
    return "type1"



def _infer_target_type_from_rule_ui(item: dict[str, Any]) -> str:
    target_type = str(item.get("target_type", "") or "").strip().lower()
    if target_type in {"type1", "type2", "both"}:
        return target_type
    return _infer_target_type_from_legacy_classes(item.get("CLASSES", None))
