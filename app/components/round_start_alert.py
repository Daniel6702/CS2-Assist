from __future__ import annotations

from typing import Any, Callable

from app.components.base import BaseComponent
from app.components.kill_sound import KillSoundComponent
from app.gsi import GameState

SoundPlayer = Callable[[str, int], None]


class RoundStartAlertComponent(BaseComponent):
    name = "round_start_alert"

    def __init__(self, sound_player: SoundPlayer | None = None) -> None:
        super().__init__()
        self._previous_phase: str | None = None
        self._sound_player = sound_player or KillSoundComponent._play

    def configure(self, config: dict[str, Any]) -> None:
        super().configure(config)

    def start(self) -> None:
        self._previous_phase = None
        super().start()

    def stop(self) -> None:
        self._previous_phase = None
        super().stop()

    def on_gsi_state(self, state: GameState) -> None:
        phase = state.round_phase
        if (
            self._enabled
            and self.runtime_gate_open()
            and self._config.get("enabled", False)
            and self._previous_phase == "freezetime"
            and phase == "live"
        ):
            self._play_alert()
        self._previous_phase = phase

    def _play_alert(self) -> None:
        file_path = str(self._config.get("sound_file", "") or "")
        if not file_path:
            return
        volume = int(self._config.get("volume", 50))
        self._sound_player(file_path, max(0, min(100, volume)))
