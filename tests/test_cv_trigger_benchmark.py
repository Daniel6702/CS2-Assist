from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CVPipelineBenchmarkTests(unittest.TestCase):
    def test_fake_frame_benchmark_writes_required_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "benchmark.json"

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/benchmark_cv_pipeline.py",
                    "--fake-frames",
                    "5",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10.0,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))

        for key in (
            "capture_ms",
            "capture_convert_ms",
            "frame_age_ms",
            "capture_fps",
            "capture_skipped_or_backpressured",
            "loop_wait_ms",
            "preprocess_ms",
            "inference_ms",
            "postprocess_ms",
            "cpu_transfer_ms",
            "selected_boxes_count",
            "rule_select_ms",
            "candidate_ms",
            "motion_ms",
            "input_emit_ms",
            "end_to_end_ms",
        ):
            self.assertIn(key, payload)

    def test_inference_facade_benchmark_writes_warmup_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "inference.json"

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/benchmark_cv_pipeline.py",
                    "--fake-frames",
                    "5",
                    "--inference-facade",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10.0,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["benchmark_mode"], "inference_facade_fake")
        self.assertEqual(payload["warmup_count"], 1)
        self.assertEqual(payload["predict_call_count"], 6)
        self.assertIn("inference_warmup_ms", payload)
        self.assertIn("inference_ms", payload)

    def test_postprocess_filter_benchmark_writes_transfer_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "postprocess.json"

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/benchmark_cv_pipeline.py",
                    "--fake-frames",
                    "5",
                    "--postprocess-filter",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10.0,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["benchmark_mode"], "postprocess_filter_fake")
        self.assertEqual(payload["source_boxes_count"], 20)
        self.assertEqual(payload["selected_boxes_count"], 10)
        self.assertIn("postprocess_ms", payload)
        self.assertIn("cpu_transfer_ms", payload)

    def test_compiled_rules_benchmark_writes_rule_selection_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "runtime-rules.json"

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/benchmark_cv_pipeline.py",
                    "--fake-frames",
                    "5",
                    "--compiled-rules",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10.0,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["benchmark_mode"], "compiled_rules_fake")
        self.assertEqual(payload["active_rule_count"], 5)
        self.assertEqual(payload["target_class_count"], 10)
        self.assertIn("rule_select_ms", payload)

    def test_input_worker_benchmark_writes_enqueue_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "input-worker.json"

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/benchmark_cv_pipeline.py",
                    "--fake-frames",
                    "5",
                    "--input-worker",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10.0,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["benchmark_mode"], "input_worker_fake")
        self.assertEqual(payload["input_click_enqueued_count"], 5)
        self.assertEqual(payload["input_press_count"], 5)
        self.assertEqual(payload["input_release_count"], 5)
        self.assertIn("input_emit_ms", payload)

    def test_scope_sampling_benchmark_writes_scope_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "scope-sampling.json"

            result = subprocess.run(
                [
                    sys.executable,
                    "tools/benchmark_cv_pipeline.py",
                    "--fake-frames",
                    "5",
                    "--scope-sampling",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10.0,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["benchmark_mode"], "scope_sampling_fake")
        self.assertEqual(payload["full_scope_count"], 5)
        self.assertEqual(payload["sampled_scope_count"], 5)
        self.assertIn("scope_full_frame_ms", payload)
        self.assertIn("scope_sample_ms", payload)


if __name__ == "__main__":
    _ = unittest.main()
