from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Final

from app.defaults import APP_ROOT


SETTINGS_DIR: Final[Path] = APP_ROOT / "profiles"
SETTINGS_FILE_NAME: Final[str] = "settings.json"


@dataclass(frozen=True, slots=True)
class AppSettings:
    cs2_game_root: str = ""


def settings_path(state_dir: Path = SETTINGS_DIR) -> Path:
    return state_dir / SETTINGS_FILE_NAME


def load_settings(state_dir: Path = SETTINGS_DIR) -> AppSettings:
    path = settings_path(state_dir)
    if not path.exists():
        return AppSettings()
    try:
        raw = json.loads(path.read_text())
    except JSONDecodeError:
        return AppSettings()
    if not isinstance(raw, dict):
        return AppSettings()
    root = raw.get("cs2_game_root", "")
    if not isinstance(root, str):
        return AppSettings()
    return AppSettings(cs2_game_root=root)


def save_settings(settings: AppSettings, state_dir: Path = SETTINGS_DIR) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = settings_path(state_dir)
    temp_path = path.with_suffix(".tmp")
    payload = {"cs2_game_root": settings.cs2_game_root}
    temp_path.write_text(json.dumps(payload, indent=4))
    temp_path.replace(path)
