from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from .metrics import CVPerfStats, disabled_perf_stats
from .roi import CaptureRegion


@dataclass(frozen=True, slots=True)
class CaptureFrame:
    data: Any
    region: CaptureRegion
    captured_at_ns: int
    sequence: int


class LatestFrameBuffer:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._frame: CaptureFrame | None = None
        self._closed = False
        self.backpressure_count = 0

    def put(self, frame: CaptureFrame, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while self._frame is not None and not self._closed:
                self.backpressure_count += 1
                if deadline is None:
                    self._condition.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    return False
                self._condition.wait(remaining)
            if self._closed:
                return False
            self._frame = frame
            self._condition.notify_all()
            return True

    def get(self, timeout: float | None = None) -> CaptureFrame | None:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while self._frame is None and not self._closed:
                if deadline is None:
                    self._condition.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    return None
                self._condition.wait(remaining)
            frame = self._frame
            self._frame = None
            self._condition.notify_all()
            return frame

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()


class Grab(threading.Thread):
    def __init__(
        self,
        monitor: dict[str, int],
        status_callback: Any = None,
        region: CaptureRegion | None = None,
        perf_stats: CVPerfStats | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self.monitor = monitor
        self.status_callback = status_callback
        self.region = region or CaptureRegion(
            monitor_left=int(monitor.get("left", 0)),
            monitor_top=int(monitor.get("top", 0)),
            roi_left=0,
            roi_top=0,
            width=int(monitor.get("width", 1)),
            height=int(monitor.get("height", 1)),
        )
        self.buffer = LatestFrameBuffer()
        self.perf_stats = perf_stats or disabled_perf_stats()
        self.run_flag = True
        self._last_error_text: str | None = None
        self._last_error_report_at = 0.0
        self._sequence = 0

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
                            with self.perf_stats.timer("capture_ms"):
                                img = sct.grab(self.region.as_capture_dict())
                            with self.perf_stats.timer("capture_convert_ms"):
                                frame = cv2.cvtColor(np.asarray(img, np.uint8), cv2.COLOR_BGRA2BGR)
                            self._sequence += 1
                            self.buffer.put(
                                CaptureFrame(
                                    data=frame,
                                    region=self.region,
                                    captured_at_ns=time.perf_counter_ns(),
                                    sequence=self._sequence,
                                ),
                            )
                            self._last_error_text = None
                        except Exception as exc:
                            self._report_warning(exc)
                            time.sleep(0.05)
                            break
            except Exception as exc:
                self._report_warning(exc)
                time.sleep(0.1)

    def frame(self):
        return self.buffer.get(timeout=0.0)

    def next_frame(self, timeout: float | None = None) -> CaptureFrame | None:
        return self.buffer.get(timeout=timeout)

    def stop(self) -> None:
        self.run_flag = False
        self.buffer.close()
