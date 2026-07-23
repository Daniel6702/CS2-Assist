from __future__ import annotations

import threading
import time
from typing import Any, Callable

import numpy as np
from mss import mss

from app.components.base import BaseComponent
from app.components.kill_sound import KillSoundComponent
from app.gsi import GameState

# Reference resolution used for the bomb icon pixel offsets.
# Actual offset is scaled proportionally from game resolution.
_REF_W = 2560
_REF_H = 1440
_OFFSET_FROM_CENTER_X = -10
_OFFSET_FROM_CENTER_Y = 24
_CAPTURE_SIZE = 14
_POLL_INTERVAL = 0.1
_CONFIRM_FRAMES = 2
_SCAN_GRACE_SECONDS = 3  # wait after freezetime→live before scanning
_DETECTION_DELAY = 0.6  # compensate for poll+confirm delay after plant


class BombTimerComponent(BaseComponent):
    name = "bomb_timer"

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False

        self._team: str | None = None
        self._defusekit: bool | None = None
        self._bomb_planted = False
        self._plant_time: float = 0.0
        self._remaining: int = 0
        self._played_10s = False
        self._played_5s = False

        self._round_phase: str | None = None
        self._live_since: float = 0.0

        # Config
        self._game_w = _REF_W
        self._game_h = _REF_H
        self._bomb_seconds = 40
        self._ten_sec_enabled = True
        self._ten_sec_file = ""
        self._ten_sec_vol = 50
        self._five_sec_enabled = True
        self._five_sec_file = ""
        self._five_sec_vol = 50

        # Sound callbacks (set by MainWindow for UI-side logging)
        self._on_10s_callback: Callable[[], None] | None = None
        self._on_5s_callback: Callable[[], None] | None = None

    # ---- public helpers for MainWindow -----------------------------------

    def set_on_10s_callback(self, cb: Callable[[], None]) -> None:
        self._on_10s_callback = cb

    def set_on_5s_callback(self, cb: Callable[[], None]) -> None:
        self._on_5s_callback = cb

    # ---- BaseComponent overrides -----------------------------------------

    def configure(self, config: dict[str, Any]) -> None:
        super().configure(config)
        with self._lock:
            gr = config.get("game_resolution", {}) or {}
            self._game_w = max(1, int(gr.get("width", _REF_W)))
            self._game_h = max(1, int(gr.get("height", _REF_H)))
            self._bomb_seconds = max(10, int(config.get("timer_seconds", 40)))
            self._ten_sec_enabled = bool(config.get("warning_10s_enabled", True))
            self._ten_sec_file = str(config.get("warning_10s_file", "") or "")
            self._ten_sec_vol = int(config.get("warning_10s_volume", 50))
            self._five_sec_enabled = bool(config.get("warning_5s_enabled", True))
            self._five_sec_file = str(config.get("warning_5s_file", "") or "")
            self._five_sec_vol = int(config.get("warning_5s_volume", 50))

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._running = True
            self._bomb_planted = False
            self._remaining = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        super().start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._bomb_planted = False
            self._remaining = 0
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        super().stop()

    def on_gsi_state(self, state: GameState) -> None:
        with self._lock:
            self._team = state.team
            self._defusekit = state.defusekit
            prev_phase = self._round_phase
            self._round_phase = state.round_phase
            if prev_phase != "live" and state.round_phase == "live":
                self._live_since = time.monotonic()

    def on_runtime_gate_changed(self, open_: bool, reason: str) -> None:
        if open_:
            return
        with self._lock:
            self._bomb_planted = False
            self._remaining = 0

    # ---- external state poll (called from MainWindow tick) ---------------

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "bomb_planted": self._bomb_planted,
                "remaining": self._remaining,
                "team": self._team,
                "defusekit": self._defusekit,
            }

    # ---- internal --------------------------------------------------------

    def _run(self) -> None:
        time.sleep(0.5)  # let UI settle
        consecutive_red = 0

        with mss() as sct:
            while self._running:
                monitor = sct.monitors[1]
                cx = monitor["width"] // 2
                cy = monitor["top"]
                half = _CAPTURE_SIZE // 2

                with self._lock:
                    ox = _OFFSET_FROM_CENTER_X * self._game_w // _REF_W
                    oy = _OFFSET_FROM_CENTER_Y * self._game_h // _REF_H
                    bomb_planted = self._bomb_planted
                    plant_time = self._plant_time
                    round_phase = self._round_phase
                    live_since = self._live_since

                if not self.automation_permitted():
                    consecutive_red = 0
                    time.sleep(_POLL_INTERVAL)
                    continue

                if not bomb_planted:
                    if round_phase is not None and round_phase != "live":
                        consecutive_red = 0
                        time.sleep(_POLL_INTERVAL)
                        continue
                    # Grace period after freezetime→live (red freeze timer)
                    if live_since > 0 and time.monotonic() - live_since < _SCAN_GRACE_SECONDS:
                        consecutive_red = 0
                        time.sleep(_POLL_INTERVAL)
                        continue

                    # ---- scan for bomb plant ------------------------------
                    try:
                        region = {
                            "left": cx + ox - half,
                            "top": cy + oy - half,
                            "width": _CAPTURE_SIZE,
                            "height": _CAPTURE_SIZE,
                        }
                        img = sct.grab(region)
                        frame = np.array(img, dtype=np.uint8)
                    except Exception:
                        time.sleep(_POLL_INTERVAL)
                        continue

                    if self._frame_is_red(frame):
                        consecutive_red += 1
                    else:
                        consecutive_red = 0

                    if consecutive_red >= _CONFIRM_FRAMES:
                        with self._lock:
                            self._bomb_planted = True
                            self._plant_time = time.monotonic() - _DETECTION_DELAY
                            self._remaining = self._bomb_seconds
                            self._played_10s = False
                            self._played_5s = False
                        self.status(f"Bomb planted! {self._bomb_seconds}s timer started.")

                else:
                    # ---- countdown ----------------------------------------
                    now = time.monotonic()
                    elapsed = now - plant_time
                    rem = int(max(0, self._bomb_seconds - elapsed))
                    with self._lock:
                        self._remaining = rem

                    # bomb exploded / defused → reset
                    # Also reset if round left "live" (e.g. bomb defused)
                    round_over = round_phase is not None and round_phase != "live"
                    if rem <= 0 or round_over:
                        with self._lock:
                            self._bomb_planted = False
                            self._remaining = 0
                        consecutive_red = 0
                        time.sleep(_POLL_INTERVAL)
                        continue

                    if rem <= 5 and not self._played_5s and self._five_sec_enabled and self._five_sec_file:
                        self._played_5s = True
                        self._play_warning(self._five_sec_file, self._five_sec_vol)
                        if self._on_5s_callback:
                            self._on_5s_callback()

                    if rem <= 10 and not self._played_10s and self._ten_sec_enabled and self._ten_sec_file:
                        self._played_10s = True
                        self._play_warning(self._ten_sec_file, self._ten_sec_vol)
                        if self._on_10s_callback:
                            self._on_10s_callback()

                    time.sleep(_POLL_INTERVAL)

                time.sleep(_POLL_INTERVAL)

    # -----------------------------------------------------------------
    #  Colour detection
    # -----------------------------------------------------------------

    @staticmethod
    def _frame_is_red(frame: np.ndarray) -> bool:
        """Return True when the sampled region looks red (bomb planted).

        ``frame`` is BGRA uint8 with shape (H, W, 4).
        Before plant the icon is orange  (R~255, G~140-180, B~0-50).
        After  plant the icon is red     (R~200-255,  G~0-50, B~0-50).

        Counts INDIVIDUAL red-dominant pixels instead of averaging the whole
        region — a small red icon on a dark background is detected even
        when the background pixels outnumber the icon pixels 10:1.
        """
        r = frame[:, :, 2].astype(np.int32)
        g = frame[:, :, 1].astype(np.int32)
        b = frame[:, :, 0].astype(np.int32)
        # Deep saturated red — bomb icon in red phase has R>>G,B.
        # Orange/light-red UI elements have much higher G and won't pass.
        red_mask = (r > 160) & (r > g * 2.5) & (r > b * 2.5)
        return int(red_mask.sum()) >= 5

    # -----------------------------------------------------------------
    #  Sound playback (reuses the same ffplay logic as KillSoundComponent)
    # -----------------------------------------------------------------

    @staticmethod
    def _play_warning(path: str, volume: int) -> None:
        KillSoundComponent._play(path, volume)
