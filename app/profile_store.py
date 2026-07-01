from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.common import deep_copy
from app.defaults import PROFILES_DIR, default_profile


_SAFE_RE = re.compile(r"[^a-zA-Z0-9_-]+")


class ProfileStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or PROFILES_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self.ensure_default_profile()

    def ensure_default_profile(self) -> None:
        if not self.list_profile_names():
            self.save_profile("Default", default_profile())

    def _profile_path(self, name: str) -> Path:
        safe = _SAFE_RE.sub("_", name).strip("_") or "profile"
        return self.root / f"{safe}.json"

    def list_profile_names(self) -> list[str]:
        names = [path.stem for path in sorted(self.root.glob("*.json"))]
        return names

    def load_profile(self, name: str) -> dict[str, Any]:
        path = self._profile_path(name)
        if not path.exists():
            raise FileNotFoundError(f"Profile not found: {name}")
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save_profile(self, name: str, data: dict[str, Any]) -> None:
        path = self._profile_path(name)
        payload = deep_copy(data)
        payload["name"] = name
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=4)

    def create_profile(self, name: str, source: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = deep_copy(source if source is not None else default_profile())
        payload["name"] = name
        self.save_profile(name, payload)
        return payload

    def delete_profile(self, name: str) -> None:
        path = self._profile_path(name)
        if path.exists():
            path.unlink()
        if not self.list_profile_names():
            self.ensure_default_profile()
