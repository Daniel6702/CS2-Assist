from __future__ import annotations

import unittest
from typing import Any

from app.components.cv_trigger.inference import InferenceConfig, UltralyticsInferenceEngine


class FakePredictModel:
    def __init__(self, results: list[Any]) -> None:
        self.results = results
        self.calls: list[dict[str, Any]] = []

    def predict(
        self,
        source: Any,
        *,
        conf: float,
        imgsz: int,
        device: int | str,
        stream: bool,
        verbose: bool,
    ) -> list[Any]:
        self.calls.append(
            {
                "source": source,
                "conf": conf,
                "imgsz": imgsz,
                "device": device,
                "stream": stream,
                "verbose": verbose,
            }
        )
        return self.results


class UltralyticsInferenceEngineTests(unittest.TestCase):
    def test_predict_uses_current_streaming_arguments(self) -> None:
        result = object()
        model = FakePredictModel([result])
        engine = UltralyticsInferenceEngine(
            model=model,
            config=InferenceConfig(confidence=0.42, image_size=512, device=0),
        )

        predicted = engine.predict("frame")

        self.assertIs(predicted, result)
        self.assertEqual(
            model.calls,
            [
                {
                    "source": "frame",
                    "conf": 0.42,
                    "imgsz": 512,
                    "device": 0,
                    "stream": True,
                    "verbose": False,
                }
            ],
        )

    def test_warmup_calls_predict_once(self) -> None:
        model = FakePredictModel([object()])
        engine = UltralyticsInferenceEngine(
            model=model,
            config=InferenceConfig(confidence=0.15, image_size=384, device="cpu"),
        )

        engine.warmup("warm-frame")

        self.assertEqual(engine.warmup_count, 1)
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(model.calls[0]["source"], "warm-frame")

    def test_empty_prediction_stream_propagates_stop_iteration(self) -> None:
        model = FakePredictModel([])
        engine = UltralyticsInferenceEngine(
            model=model,
            config=InferenceConfig(confidence=0.15, image_size=384, device="cpu"),
        )

        with self.assertRaises(StopIteration):
            engine.predict("frame")


if __name__ == "__main__":
    _ = unittest.main()
