from __future__ import annotations

import threading
import time
from typing import Any


class Grab(threading.Thread):
    def __init__(self, monitor: dict[str, int], status_callback: Any = None) -> None:
        super().__init__(daemon=True)
        self.monitor = monitor
        self.status_callback = status_callback
        self.frame_data = None
        self.lock = threading.Lock()
        self.run_flag = True
        self._last_error_text: str | None = None
        self._last_error_report_at = 0.0

    def _report_warning(self, exc: Exception) -> None:
        text = f"Capture warning: {exc}"
        now = time.time()
        if text == self._last_error_text and (now - self._last_error_report_at) < 2.0:
            return
        self._last_error_text = text
        self._last_error_report_at = now
        if self.status_callback is not None:
            try:
                self.status_callback(text, "warning")
            except Exception:
                pass

    def run(self) -> None:
        import cv2
        import mss
        import numpy as np

        while self.run_flag:
            try:
                with mss.mss() as sct:
                    while self.run_flag:
                        try:
                            img = sct.grab(self.monitor)
                            frame = cv2.cvtColor(np.asarray(img, np.uint8), cv2.COLOR_BGRA2BGR)
                            with self.lock:
                                self.frame_data = frame
                            self._last_error_text = None
                        except Exception as exc:
                            self._report_warning(exc)
                            time.sleep(0.05)
                            break
            except Exception as exc:
                self._report_warning(exc)
                time.sleep(0.1)

    def frame(self):
        with self.lock:
            return self.frame_data

    def stop(self) -> None:
        self.run_flag = False
