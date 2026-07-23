from __future__ import annotations

import threading
from dataclasses import dataclass
from collections.abc import Callable
from typing import Any, Final, Literal

from app.components.base import BaseComponent
from app.gsi import GameState


SNIPER_WEAPONS: Final[frozenset[str]] = frozenset({"weapon_awp", "weapon_ssg08"})
SNIPER_CROSSHAIR_STRETCH_FILTER: Final[Literal["linear"]] = "linear"
ScopeStateProvider = Callable[[], bool | None]


@dataclass(frozen=True, slots=True)
class SniperCrosshairOverlayState:
    visible: bool
    crosshair_code: str
    game_width: int
    game_height: int
    display_width: int
    display_height: int
    stretched: bool


def sniper_crosshair_visible(*, enabled: bool, current_weapon: str | None, scope_visible: bool) -> bool:
    if not enabled or not scope_visible or current_weapon is None:
        return False
    return current_weapon.strip().lower() in SNIPER_WEAPONS


def scope_state_allows_overlay(*, scope_state: bool | None, stay_when_scoped: bool) -> bool:
    return scope_state is False or (stay_when_scoped and scope_state is True)


def _resolution(value: Any, default: tuple[int, int]) -> tuple[int, int]:
    if not isinstance(value, dict):
        return default
    return (
        max(1, int(value.get("width", default[0]) or default[0])),
        max(1, int(value.get("height", default[1]) or default[1])),
    )


class SniperCrosshairComponent(BaseComponent):
    name = "sniper_crosshair"

    def __init__(self) -> None:
        super().__init__()
        self._state_lock = threading.RLock()
        self._current_weapon: str | None = None
        self._scope_state_provider: ScopeStateProvider | None = None
        self._crosshair_code = ""
        self._stay_when_scoped = False
        self._game_resolution = (1920, 1080)
        self._display_resolution = (1920, 1080)
        self._stretched = True

    def configure(self, config: dict[str, Any]) -> None:
        super().configure(config)
        with self._state_lock:
            self._crosshair_code = str(config.get("crosshair_code", "") or "")
            self._stay_when_scoped = bool(config.get("stay_when_scoped", False))
            self._game_resolution = _resolution(config.get("game_resolution"), (1920, 1080))
            self._display_resolution = _resolution(config.get("display_resolution"), self._game_resolution)
            self._stretched = bool(config.get("game_resolution_stretched", config.get("stretched", True)))
            provider = config.get("scope_state_provider")
            self._scope_state_provider = provider if callable(provider) else None

    def on_gsi_state(self, state: GameState) -> None:
        with self._state_lock:
            self._current_weapon = state.current_weapon

    def overlay_state(self) -> SniperCrosshairOverlayState:
        with self._state_lock:
            game_width, game_height = self._game_resolution
            display_width, display_height = self._display_resolution
            provider = self._scope_state_provider
            scope_state = None if provider is None else provider()
            return SniperCrosshairOverlayState(
                visible=sniper_crosshair_visible(
                    enabled=self.enabled,
                    current_weapon=self._current_weapon,
                    scope_visible=scope_state_allows_overlay(
                        scope_state=scope_state,
                        stay_when_scoped=self._stay_when_scoped,
                    ),
                ),
                crosshair_code=self._crosshair_code,
                game_width=game_width,
                game_height=game_height,
                display_width=display_width,
                display_height=display_height,
                stretched=self._stretched,
            )
