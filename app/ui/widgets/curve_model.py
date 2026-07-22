from __future__ import annotations

import re
from typing import Any

CurveDict = dict[str, Any]


def clamp_sort_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for x, y in points:
        cx = max(0.0, min(1.0, float(x)))
        cy = max(0.0, min(1.0, float(y)))
        out.append((cx, cy))
    out.sort(key=lambda p: p[0])
    return out


def ensure_endpoints(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not points:
        return [(0.0, 0.0), (1.0, 1.0)]
    first_y = points[0][1]
    last_y = points[-1][1]
    result = list(points)
    if result[0][0] != 0.0:
        result.insert(0, (0.0, first_y))
    if result[-1][0] != 1.0:
        result.append((1.0, last_y))
    return result


def id_from_label(label: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", label.strip()).strip("_").lower()
    return slug if slug else "unnamed"


def unique_id(label: str, existing_ids: set[str]) -> str:
    base = id_from_label(label)
    if base not in existing_ids:
        return base
    suffix = 2
    while f"{base}_{suffix}" in existing_ids:
        suffix += 1
    return f"{base}_{suffix}"


def normalize_curve(raw: Any, fallback_label: str = "") -> CurveDict | None:
    points_raw: Any = None
    label = fallback_label

    if isinstance(raw, dict):
        label = str(raw.get("label", fallback_label or ""))
        points_raw = raw.get("points")
    elif isinstance(raw, (list, tuple)):
        points_raw = raw

    if not isinstance(points_raw, (list, tuple)) or len(points_raw) < 2:
        return None

    parsed: list[tuple[float, float]] = []
    for item in points_raw:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            return None
        try:
            parsed.append((float(item[0]), float(item[1])))
        except (TypeError, ValueError):
            return None

    sorted_points = clamp_sort_points(parsed)
    return {"label": label, "points": ensure_endpoints(sorted_points)}


def load_curves(raw: Any) -> dict[str, CurveDict]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, CurveDict] = {}
    for curve_id, raw_value in raw.items():
        if isinstance(curve_id, str) and curve_id.strip():
            normalized = normalize_curve(raw_value, fallback_label=curve_id)
            if normalized is not None:
                normalized["_id"] = curve_id
                out[curve_id] = normalized
    return out


def extract_curves(curves: dict[str, CurveDict]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for curve_id, curve in curves.items():
        out[curve_id] = {
            "label": str(curve.get("label", curve_id)),
            "points": [[float(point[0]), float(point[1])] for point in curve.get("points", [])],
        }
    return out
