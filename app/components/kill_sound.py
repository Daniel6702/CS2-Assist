from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from typing import Any

from app.components.base import BaseComponent
from app.gsi import GameState

_FADE_DURATION = 1.5


def _cleanup(path: str) -> None:
    try:
        os.unlink(path)
    except Exception:
        pass


class KillSoundComponent(BaseComponent):
    name = "kill_sound"

    def __init__(self) -> None:
        super().__init__()
        self._last_kills: int | None = None

    def configure(self, config: dict[str, Any]) -> None:
        super().configure(config)

    def on_gsi_state(self, state: GameState) -> None:
        new_kills = state.kills
        if new_kills is None:
            return
        if self._last_kills is not None and new_kills > self._last_kills:
            self._on_kill()
        self._last_kills = new_kills

    def _on_kill(self) -> None:
        cfg = self._config
        if not cfg.get("enabled", False):
            return
        if not self._enabled:
            return
        file_path = str(cfg.get("sound_file", "") or "")
        if not file_path:
            return
        volume = int(cfg.get("volume", 50))
        self._play(file_path, max(0, min(100, volume)))

    @staticmethod
    def _play(path: str, volume: int) -> None:
        vol = max(0, min(100, volume))

        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet",
                 "-show_entries", "format=duration",
                 "-of", "csv=p=0", path],
                capture_output=True, text=True, timeout=5.0,
            )
            raw = result.stdout.strip()
            if not raw:
                return
            duration = float(raw)
            fade_dur = min(_FADE_DURATION, duration * 0.35)
            if fade_dur < 0.08:
                return
            fd, temp_file = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            fade_start = duration - fade_dur
            vol_mult = vol / 100.0
            filter_str = (
                f"volume={vol_mult},"
                f"afade=t=out:st={fade_start:.2f}:d={fade_dur:.2f}"
            )
            proc = subprocess.run(
                ["ffmpeg", "-y", "-i", path, "-af", filter_str, temp_file],
                capture_output=True, timeout=10.0,
            )
            if proc.returncode != 0:
                _cleanup(temp_file)
                return
            subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", "-volume", str(vol), temp_file],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            threading.Timer(5.0, _cleanup, args=(temp_file,)).start()
        except Exception:
            pass
