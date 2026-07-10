from __future__ import annotations

from copy import deepcopy
from typing import Any

PRESET_CURVES: dict[str, dict[str, Any]] = {
    "constant_50": {
        "label": "Constant 50%",
        "points": [[0.0, 0.5], [1.0, 0.5]],
    },
    "linear": {
        "label": "Linear",
        "points": [
            [0.0, 0.0],
            [0.125, 0.125],
            [0.25, 0.25],
            [0.375, 0.375],
            [0.5, 0.5],
            [0.625, 0.625],
            [0.75, 0.75],
            [0.875, 0.875],
            [1.0, 1.0],
        ],
    },
    "exponential": {
        "label": "Exponential",
        "points": [
            [0.0, 0.0],
            [0.125, 0.016],
            [0.25, 0.063],
            [0.375, 0.141],
            [0.5, 0.25],
            [0.625, 0.391],
            [0.75, 0.563],
            [0.875, 0.766],
            [1.0, 1.0],
        ],
    },
}

LEGACY_CURVE_MAP: dict[str, str] = {
    "proportional": "linear",
    "linear": "linear",
    "accelerating": "exponential",
    "exponential": "exponential",
    "constant": "constant_50",
}


def build_curve_library() -> dict[str, dict[str, Any]]:
    return deepcopy(PRESET_CURVES)


def legacy_response_curve_to_id(value: Any) -> str:
    legacy = str(value or "").strip().lower()
    return LEGACY_CURVE_MAP.get(legacy, "linear")
