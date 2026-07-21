from __future__ import annotations

import threading
import time
import unittest

from app.components.cv_trigger.capture import CaptureFrame, LatestFrameBuffer
from app.components.cv_trigger.roi import CaptureRegion


class LatestFrameBufferTests(unittest.TestCase):
    def _frame(self, sequence: int) -> CaptureFrame:
        return CaptureFrame(
            data=f"frame-{sequence}",
            region=CaptureRegion(monitor_left=0, monitor_top=0, roi_left=0, roi_top=0, width=10, height=10),
            captured_at_ns=time.perf_counter_ns(),
            sequence=sequence,
        )

    def test_single_slot_blocks_second_put_until_consumer_takes_frame(self) -> None:
        buffer = LatestFrameBuffer()
        put_finished = threading.Event()

        self.assertTrue(buffer.put(self._frame(1), timeout=0.01))

        def put_second() -> None:
            if buffer.put(self._frame(2), timeout=0.5):
                put_finished.set()

        thread = threading.Thread(target=put_second)
        thread.start()
        time.sleep(0.05)
        self.assertFalse(put_finished.is_set())

        first = buffer.get(timeout=0.1)
        thread.join(timeout=1.0)
        second = buffer.get(timeout=0.1)

        self.assertEqual(first.sequence if first else None, 1)
        self.assertTrue(put_finished.is_set())
        self.assertEqual(second.sequence if second else None, 2)

    def test_close_wakes_waiting_consumer(self) -> None:
        buffer = LatestFrameBuffer()
        result: list[CaptureFrame | None] = []

        def wait_for_frame() -> None:
            result.append(buffer.get(timeout=1.0))

        thread = threading.Thread(target=wait_for_frame)
        thread.start()
        time.sleep(0.05)
        buffer.close()
        thread.join(timeout=1.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [None])

    def test_close_wakes_waiting_producer(self) -> None:
        buffer = LatestFrameBuffer()
        self.assertTrue(buffer.put(self._frame(1), timeout=0.01))
        result: list[bool] = []

        def put_second() -> None:
            result.append(buffer.put(self._frame(2), timeout=1.0))

        thread = threading.Thread(target=put_second)
        thread.start()
        time.sleep(0.05)
        buffer.close()
        thread.join(timeout=1.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [False])


if __name__ == "__main__":
    _ = unittest.main()
