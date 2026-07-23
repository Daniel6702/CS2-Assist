from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Final, Protocol

from app.components.base import BaseComponent


MATCH_FOUND_MARKER: Final[str] = "Server confirmed all players"
ACCEPT_BUTTON_COLOR: Final[tuple[int, int, int]] = (54, 183, 82)
COLOR_TOLERANCE: Final[int] = 20
DEFAULT_WAITING_SECONDS: Final[float] = 5.0
DEFAULT_CLICK_HOLD_MS: Final[int] = 24
DEFAULT_POLL_INTERVAL_SECONDS: Final[float] = 0.10
ACCEPT_BUTTON_Y_DIVISOR: Final[float] = 2.215


class AcceptClicker(Protocol):
    def click_at(self, x: int, y: int, hold_ms: int) -> None: ...


class ScreenProbe(Protocol):
    def size(self) -> tuple[int, int]: ...

    def pixel_at(self, x: int, y: int) -> tuple[int, int, int]: ...


class _PyAutoGuiClicker:
    def __init__(self) -> None:
        import pyautogui

        self._pyautogui = pyautogui

    def click_at(self, x: int, y: int, hold_ms: int) -> None:
        previous = self._pyautogui.position()
        self._pyautogui.moveTo(x, y)
        self._pyautogui.mouseDown(button="left")
        time.sleep(max(1, hold_ms) / 1000.0)
        self._pyautogui.mouseUp(button="left")
        self._pyautogui.moveTo(previous.x, previous.y)


class _PyAutoGuiScreenProbe:
    def __init__(self) -> None:
        import pyautogui

        self._pyautogui = pyautogui

    def size(self) -> tuple[int, int]:
        width, height = self._pyautogui.size()
        return int(width), int(height)

    def pixel_at(self, x: int, y: int) -> tuple[int, int, int]:
        pixel = self._pyautogui.screenshot(region=(x, y, 1, 1)).getpixel((0, 0))
        return int(pixel[0]), int(pixel[1]), int(pixel[2])


def _color_matches(actual: tuple[int, int, int]) -> bool:
    return all(abs(channel - target) <= COLOR_TOLERANCE for channel, target in zip(actual, ACCEPT_BUTTON_COLOR))


def _accept_button_position(screen: ScreenProbe) -> tuple[int, int]:
    width, height = screen.size()
    return int(round(width / 2.0)), int(round(height / ACCEPT_BUTTON_Y_DIVISOR))


class AutoAcceptComponent(BaseComponent):
    name = "auto_accept"

    def __init__(self, *, clicker: AcceptClicker | None = None, screen: ScreenProbe | None = None) -> None:
        super().__init__()
        self._clicker = clicker
        self._screen = screen
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._state_lock = threading.RLock()
        self._console_log_path = Path()
        self._waiting_time_seconds = DEFAULT_WAITING_SECONDS
        self._click_hold_ms = DEFAULT_CLICK_HOLD_MS
        self._poll_interval_seconds = DEFAULT_POLL_INTERVAL_SECONDS
        self._last_offset = 0
        self._last_size = -1

    def configure(self, config: dict[str, Any]) -> None:
        super().configure(config)
        with self._state_lock:
            self._console_log_path = Path(str(config.get("console_log_path", "") or "")).expanduser()
            self._waiting_time_seconds = max(0.1, float(config.get("waiting_time_seconds", DEFAULT_WAITING_SECONDS) or DEFAULT_WAITING_SECONDS))
            self._click_hold_ms = max(1, int(config.get("click_hold_ms", DEFAULT_CLICK_HOLD_MS) or DEFAULT_CLICK_HOLD_MS))
            self._poll_interval_seconds = max(
                0.02,
                float(config.get("poll_interval_seconds", DEFAULT_POLL_INTERVAL_SECONDS) or DEFAULT_POLL_INTERVAL_SECONDS),
            )

    def start(self) -> None:
        if self._thread is not None:
            return
        super().start()
        if self._clicker is None:
            self._clicker = _PyAutoGuiClicker()
        if self._screen is None:
            self._screen = _PyAutoGuiScreenProbe()
        self._reset_tail_offset()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.status("Started. Watching CS2 console.log for match acceptance.")

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        super().stop()
        self.status("Stopped.")

    def _settings(self) -> tuple[Path, float, int, float]:
        with self._state_lock:
            return (
                self._console_log_path,
                self._waiting_time_seconds,
                self._click_hold_ms,
                self._poll_interval_seconds,
            )

    def _reset_tail_offset(self) -> None:
        path, _waiting, _hold, _poll = self._settings()
        try:
            self._last_size = path.stat().st_size
        except OSError:
            self._last_size = -1
            self._last_offset = 0
            return
        self._last_offset = self._last_size

    def _run(self) -> None:
        while not self._stop.is_set():
            path, waiting_time_seconds, click_hold_ms, poll_interval_seconds = self._settings()
            for line in self._read_new_lines(path):
                if MATCH_FOUND_MARKER in line and self.automation_permitted():
                    self._try_accept(waiting_time_seconds, click_hold_ms)
            self._stop.wait(poll_interval_seconds)

    def _read_new_lines(self, path: Path) -> list[str]:
        try:
            size = path.stat().st_size
        except OSError:
            self._last_size = -1
            self._last_offset = 0
            return []
        if size == self._last_size:
            return []
        if size < self._last_offset:
            self._last_offset = 0
        self._last_size = size
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                handle.seek(self._last_offset)
                lines = handle.readlines()
                self._last_offset = handle.tell()
        except OSError:
            return []
        return [line.rstrip("\n") for line in lines if line.strip()]

    def _try_accept(self, waiting_time_seconds: float, click_hold_ms: int) -> None:
        screen = self._screen
        clicker = self._clicker
        if screen is None or clicker is None:
            return
        deadline = time.monotonic() + waiting_time_seconds
        while time.monotonic() <= deadline and not self._stop.is_set() and self.automation_permitted():
            x, y = _accept_button_position(screen)
            if _color_matches(screen.pixel_at(x, y)):
                clicker.click_at(x, y, click_hold_ms)
                self.status("Clicked Accept.")
                return
            self._stop.wait(0.025)
