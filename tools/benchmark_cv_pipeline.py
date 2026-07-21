#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# How to run:
#   PYTHONPATH=. python tools/benchmark_cv_pipeline.py --fake-frames 30 --output .omo/evidence/cv-benchmark.json

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.components.cv_trigger.inference import InferenceConfig, UltralyticsInferenceEngine  # noqa: E402
from app.components.cv_trigger.input_worker import InputWorker  # noqa: E402
from app.components.cv_trigger.detection import ScopeDetector, scope_corner_patches  # noqa: E402
from app.components.cv_trigger.metrics import CVPerfStats, JSONValue  # noqa: E402
from app.components.cv_trigger.postprocess import extract_filtered_detections  # noqa: E402
from app.components.cv_trigger.runtime_rules import compile_rules, highest_priority_rules  # noqa: E402

REQUIRED_TIMINGS = (
    "capture_ms",
    "capture_convert_ms",
    "frame_age_ms",
    "loop_wait_ms",
    "preprocess_ms",
    "inference_ms",
    "postprocess_ms",
    "cpu_transfer_ms",
    "rule_select_ms",
    "candidate_ms",
    "motion_ms",
    "input_emit_ms",
    "end_to_end_ms",
)


def _spin_once() -> None:
    start = time.perf_counter_ns()
    while time.perf_counter_ns() - start < 1_000:
        pass


class FakePredictModel:
    def __init__(self) -> None:
        self.calls = 0

    def predict(
        self,
        source: Any,
        *,
        conf: float,
        imgsz: int,
        device: int | str,
        stream: bool,
        verbose: bool,
    ) -> list[dict[str, JSONValue]]:
        self.calls += 1
        _spin_once()
        return [
            {
                "source_type": type(source).__name__,
                "conf": conf,
                "imgsz": imgsz,
                "device": str(device),
                "stream": stream,
                "verbose": verbose,
            }
        ]


def run_fake_frame_benchmark(frame_count: int) -> dict[str, JSONValue]:
    stats = CVPerfStats(enabled=True)
    started = time.perf_counter()
    for _ in range(max(1, frame_count)):
        frame_started = time.perf_counter_ns()
        for name in REQUIRED_TIMINGS:
            with stats.timer(name):
                _spin_once()
        stats.record_count("selected_boxes_count", 0)
        stats.record_count("capture_skipped_or_backpressured", 0)
        elapsed_ms = (time.perf_counter_ns() - frame_started) / 1_000_000.0
        stats.record_ms("end_to_end_ms", elapsed_ms)
    elapsed = max(time.perf_counter() - started, 1e-9)
    summary = stats.summary(
        extra={
            "benchmark_mode": "fake_frames",
            "frame_count": max(1, frame_count),
            "capture_fps": max(1, frame_count) / elapsed,
        },
    )
    return summary


def run_inference_facade_benchmark(frame_count: int) -> dict[str, JSONValue]:
    stats = CVPerfStats(enabled=True)
    model = FakePredictModel()
    engine = UltralyticsInferenceEngine(
        model=model,
        config=InferenceConfig(confidence=0.15, image_size=512, device="cpu"),
    )
    frame = [[0, 0, 0]]
    with stats.timer("inference_warmup_ms"):
        engine.warmup(frame)
    for _ in range(max(1, frame_count)):
        with stats.timer("inference_ms"):
            engine.predict(frame)
    return stats.summary(
        extra={
            "benchmark_mode": "inference_facade_fake",
            "frame_count": max(1, frame_count),
            "predict_call_count": model.calls,
            "warmup_count": engine.warmup_count,
        },
    )


class FakeBoxes:
    def __init__(self) -> None:
        import torch

        self.xyxy = torch.tensor(
            [
                [10.0, 20.0, 30.0, 40.0],
                [50.0, 60.0, 70.0, 80.0],
                [90.0, 100.0, 110.0, 120.0],
                [130.0, 140.0, 150.0, 160.0],
            ]
        )
        self.cls = torch.tensor([1.0, 2.0, 3.0, 4.0])


class FakeMouse:
    def __init__(self) -> None:
        self.press_count = 0
        self.release_count = 0

    def press_left(self) -> None:
        self.press_count += 1

    def release_left(self) -> None:
        self.release_count += 1


def run_postprocess_filter_benchmark(frame_count: int) -> dict[str, JSONValue]:
    stats = CVPerfStats(enabled=True)
    source_count = 0
    selected_count = 0
    for _ in range(max(1, frame_count)):
        with stats.timer("postprocess_ms"):
            with stats.timer("cpu_transfer_ms"):
                extracted = extract_filtered_detections(
                    boxes=FakeBoxes(),
                    target_class_ids={2, 4},
                    roi_left=5,
                    roi_top=7,
                )
        source_count += extracted.source_count
        selected_count += extracted.selected_count
    stats.record_count("source_boxes_count", source_count)
    stats.record_count("selected_boxes_count", selected_count)
    return stats.summary(
        extra={
            "benchmark_mode": "postprocess_filter_fake",
            "frame_count": max(1, frame_count),
        },
    )


def run_compiled_rules_benchmark(frame_count: int) -> dict[str, JSONValue]:
    stats = CVPerfStats(enabled=True)
    rules = compile_rules(
        {
            "body": {
                "priority": 0,
                "activation": {"mode": "always"},
                "allowed_weapons": ["weapon_ak47"],
                "target_type": "type1",
                "only_when_scoped_visual": False,
                "auto_shoot": False,
                "spray_target_offset_enabled": True,
                "AIM_MODE": "body",
                "HEAD_OFFSET": 0.1,
                "BODY_KNEE_OFFSET": 0.5,
                "SNAP_DISTANCE": 60,
                "SETTLE_FRAMES": 2,
                "CLICK_HOLD_MS": 20,
                "COOLDOWN_MS": 350,
                "auto_shoot_aim_cooldown_ms": 200,
                "AIM_STRENGTH": 0.55,
                "AIM_CURVE_ID": "linear",
                "MAX_AIM_SPEED_PX": 30,
                "SMOOTHING_ALPHA": 0.5,
                "NOISE_AMOUNT": 1.0,
                "AUTO_SHOOT_ZONE_WIDTH": 28,
                "AUTO_SHOOT_ZONE_HEIGHT": 36,
                "AUTO_SHOOT_ZONE_Y_POS": 0.35,
            },
            "head": {
                "priority": 1,
                "activation": {"mode": "always"},
                "allowed_weapons": ["weapon_ak47"],
                "target_type": "type2",
                "only_when_scoped_visual": False,
                "auto_shoot": True,
                "spray_target_offset_enabled": False,
                "AIM_MODE": "head",
                "HEAD_OFFSET": 0.1,
                "BODY_KNEE_OFFSET": 0.5,
                "SNAP_DISTANCE": 100,
                "SETTLE_FRAMES": 2,
                "CLICK_HOLD_MS": 15,
                "COOLDOWN_MS": 250,
                "auto_shoot_aim_cooldown_ms": 250,
                "AIM_STRENGTH": 0.9,
                "AIM_CURVE_ID": "linear",
                "MAX_AIM_SPEED_PX": 35,
                "SMOOTHING_ALPHA": 0.5,
                "NOISE_AMOUNT": 1.0,
                "AUTO_SHOOT_ZONE_WIDTH": 28,
                "AUTO_SHOOT_ZONE_HEIGHT": 36,
                "AUTO_SHOOT_ZONE_Y_POS": 0.35,
            },
        },
        {"linear": {"points": [(0.0, 1.0), (1.0, 1.0)]}},
    )
    active_count = 0
    target_class_count = 0
    for _ in range(max(1, frame_count)):
        with stats.timer("rule_select_ms"):
            active = highest_priority_rules([
                rule
                for rule in rules.values()
                if rule.weapon_allowed("weapon_ak47") and rule.scope_allowed(False)
            ])
            active_count += len(active)
            for rule in active:
                target_class_count += len(rule.target_classes({"t", "ct"}))
    stats.record_count("active_rule_count", active_count)
    stats.record_count("target_class_count", target_class_count)
    return stats.summary(
        extra={
            "benchmark_mode": "compiled_rules_fake",
            "frame_count": max(1, frame_count),
        },
    )


def run_input_worker_benchmark(frame_count: int) -> dict[str, JSONValue]:
    stats = CVPerfStats(enabled=True)
    mouse = FakeMouse()
    worker = InputWorker(mouse, max_pending=max(1, frame_count + 1))
    worker.start()
    accepted_count = 0
    for _ in range(max(1, frame_count)):
        with stats.timer("input_emit_ms"):
            if worker.enqueue_click(1):
                accepted_count += 1
    deadline = time.monotonic() + 2.0
    while mouse.release_count < accepted_count and time.monotonic() < deadline:
        time.sleep(0.001)
    worker.stop(timeout=1.0)
    stats.record_count("input_click_enqueued_count", accepted_count)
    stats.record_count("input_press_count", mouse.press_count)
    stats.record_count("input_release_count", mouse.release_count)
    return stats.summary(
        extra={
            "benchmark_mode": "input_worker_fake",
            "frame_count": max(1, frame_count),
        },
    )


def _fake_scope_frame() -> Any:
    import numpy as np

    frame = np.full((100, 120, 3), 80, dtype=np.uint8)
    p = 24
    frame[0:p, 0:p] = 0
    frame[0:p, -p:] = 0
    frame[-p:, 0:p] = 0
    frame[-p:, -p:] = 0
    return frame


def run_scope_sampling_benchmark(frame_count: int) -> dict[str, JSONValue]:
    stats = CVPerfStats(enabled=True)
    frame = _fake_scope_frame()
    full_detector = ScopeDetector(engage_required=1, release_required=1)
    sampled_detector = ScopeDetector(engage_required=1, release_required=1)
    full_scope_count = 0
    sampled_scope_count = 0
    for _ in range(max(1, frame_count)):
        with stats.timer("scope_full_frame_ms"):
            if full_detector.update(frame):
                full_scope_count += 1
        with stats.timer("scope_sample_ms"):
            if sampled_detector.update_patches(scope_corner_patches(frame, sampled_detector.patch_size)):
                sampled_scope_count += 1
    stats.record_count("full_scope_count", full_scope_count)
    stats.record_count("sampled_scope_count", sampled_scope_count)
    return stats.summary(
        extra={
            "benchmark_mode": "scope_sampling_fake",
            "frame_count": max(1, frame_count),
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fake-frames", type=int, default=30)
    parser.add_argument("--inference-facade", action="store_true")
    parser.add_argument("--postprocess-filter", action="store_true")
    parser.add_argument("--compiled-rules", action="store_true")
    parser.add_argument("--input-worker", action="store_true")
    parser.add_argument("--scope-sampling", action="store_true")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.scope_sampling:
        payload = run_scope_sampling_benchmark(int(args.fake_frames))
    elif args.input_worker:
        payload = run_input_worker_benchmark(int(args.fake_frames))
    elif args.compiled_rules:
        payload = run_compiled_rules_benchmark(int(args.fake_frames))
    elif args.postprocess_filter:
        payload = run_postprocess_filter_benchmark(int(args.fake_frames))
    elif args.inference_facade:
        payload = run_inference_facade_benchmark(int(args.fake_frames))
    else:
        payload = run_fake_frame_benchmark(int(args.fake_frames))
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
