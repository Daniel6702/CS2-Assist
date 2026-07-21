from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class InferenceConfig:
    confidence: float
    image_size: int
    device: int | str
    stream: bool = True
    verbose: bool = False


class PredictModel(Protocol):
    def predict(
        self,
        source: Any,
        *,
        conf: float,
        imgsz: int,
        device: int | str,
        stream: bool,
        verbose: bool,
    ) -> Any:
        ...


class UltralyticsInferenceEngine:
    def __init__(self, *, model: PredictModel, config: InferenceConfig) -> None:
        self._model = model
        self._config = config
        self.warmup_count = 0

    def predict(self, frame: Any) -> Any:
        return next(
            iter(
                self._model.predict(
                    frame,
                    conf=self._config.confidence,
                    imgsz=self._config.image_size,
                    device=self._config.device,
                    stream=self._config.stream,
                    verbose=self._config.verbose,
                )
            )
        )

    def warmup(self, frame: Any) -> None:
        self.warmup_count += 1
        self.predict(frame)
