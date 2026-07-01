from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


def deep_get(data: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def deep_set(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def deep_copy(data: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(data)


def pretty_json(data: Any) -> str:
    return json.dumps(data, indent=4, sort_keys=False)


def parse_json_text(text: str) -> Any:
    text = text.strip()
    if not text:
        return {}
    return json.loads(text)
