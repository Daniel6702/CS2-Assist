from __future__ import annotations

import threading
import time
import unittest

from app.components.cv_trigger.input_worker import InputWorker


class FakeMouse:
    def __init__(self) -> None:
        self.events: list[str] = []
        self._lock = threading.Lock()

    def press_left(self) -> None:
        with self._lock:
            self.events.append("press")

    def release_left(self) -> None:
        with self._lock:
            self.events.append("release")

    def snapshot(self) -> list[str]:
        with self._lock:
            return list(self.events)


class InputWorkerTests(unittest.TestCase):
    def test_click_command_emits_press_then_release(self) -> None:
        mouse = FakeMouse()
        worker = InputWorker(mouse)
        worker.start()

        self.assertTrue(worker.enqueue_click(1))
        deadline = time.monotonic() + 1.0
        while mouse.snapshot() != ["press", "release"] and time.monotonic() < deadline:
            time.sleep(0.01)
        worker.stop()

        self.assertEqual(mouse.snapshot(), ["press", "release"])

    def test_stop_during_hold_releases_button(self) -> None:
        mouse = FakeMouse()
        worker = InputWorker(mouse)
        worker.start()

        self.assertTrue(worker.enqueue_click(500))
        deadline = time.monotonic() + 1.0
        while mouse.snapshot() != ["press"] and time.monotonic() < deadline:
            time.sleep(0.01)
        worker.stop(timeout=1.0)

        self.assertEqual(mouse.snapshot(), ["press", "release"])

    def test_enqueue_reports_full_queue_before_start(self) -> None:
        worker = InputWorker(FakeMouse(), max_pending=1)

        self.assertTrue(worker.enqueue_click(1))
        self.assertFalse(worker.enqueue_click(1))
        worker.stop()


if __name__ == "__main__":
    _ = unittest.main()
