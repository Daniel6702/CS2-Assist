from __future__ import annotations

import json
import unittest

from app.components.cv_trigger.metrics import CVPerfStats, disabled_perf_stats


class CVPerfStatsTests(unittest.TestCase):
    def test_records_required_metric_keys(self) -> None:
        stats = CVPerfStats(enabled=True)

        stats.record_ms("capture_ms", 2.0)
        stats.record_ms("capture_ms", 4.0)
        stats.record_count("selected_boxes_count", 3)
        stats.record_count("capture_skipped_or_backpressured", 1)

        summary = stats.summary(extra={"frame_shape": [10, 20, 3]})

        self.assertEqual(summary["capture_ms"]["count"], 2)
        self.assertEqual(summary["capture_ms"]["avg"], 3.0)
        self.assertEqual(summary["selected_boxes_count"], 3)
        self.assertEqual(summary["capture_skipped_or_backpressured"], 1)
        self.assertEqual(summary["frame_shape"], [10, 20, 3])
        json.dumps(summary)

    def test_disabled_stats_are_noop(self) -> None:
        stats = disabled_perf_stats()

        stats.record_ms("capture_ms", 10.0)
        stats.record_count("selected_boxes_count", 5)

        self.assertFalse(stats.enabled)
        self.assertEqual(stats.summary(), {})


if __name__ == "__main__":
    _ = unittest.main()
