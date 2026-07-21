from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Protocol


class ClickMouse(Protocol):
    def press_left(self) -> None:
        ...

    def release_left(self) -> None:
        ...


@dataclass(frozen=True, slots=True)
class ClickCommand:
    hold_ms: int


class InputWorker:
    def __init__(self, mouse: ClickMouse, *, max_pending: int = 8) -> None:
        self._mouse = mouse
        self._commands: queue.Queue[ClickCommand] = queue.Queue(maxsize=max(1, max_pending))
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def enqueue_click(self, hold_ms: int) -> bool:
        try:
            self._commands.put_nowait(ClickCommand(hold_ms=max(1, int(hold_ms))))
        except queue.Full:
            return False
        return True

    def stop(self, *, timeout: float = 1.0) -> None:
        self._stop.set()
        if self._started and self._thread is not threading.current_thread():
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                command = self._commands.get(timeout=0.05)
            except queue.Empty:
                continue
            self._execute_click(command)

    def _execute_click(self, command: ClickCommand) -> None:
        self._mouse.press_left()
        try:
            self._stop.wait(command.hold_ms / 1000.0)
        finally:
            self._mouse.release_left()
