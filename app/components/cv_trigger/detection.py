from __future__ import annotations

from collections import deque

import numpy as np


class ScopeDetector:
    def __init__(self, patch_size: int = 24, dark_luma_threshold: float = 18.0, dark_fraction_threshold: float = 0.92, engage_required: int = 2, release_required: int = 3) -> None:
        self.patch_size = max(4, int(patch_size))
        self.dark_luma_threshold = float(dark_luma_threshold)
        self.dark_fraction_threshold = float(dark_fraction_threshold)
        self.engage_required = max(1, int(engage_required))
        self.release_required = max(1, int(release_required))
        self._scoped = False
        self._dark_streak = 0
        self._bright_streak = 0

    def update(self, frame: np.ndarray) -> bool:
        if frame is None or getattr(frame, "ndim", 0) != 3:
            return self._scoped

        h, w = frame.shape[:2]
        if h < self.patch_size * 2 or w < self.patch_size * 2:
            return self._scoped

        p = self.patch_size
        patches = [
            frame[0:p, 0:p],
            frame[0:p, w - p:w],
            frame[h - p:h, 0:p],
            frame[h - p:h, w - p:w],
        ]

        dark_corners = 0
        for patch in patches:
            if patch.size == 0:
                continue
            luma = 0.114 * patch[:, :, 0].astype(np.float32) + 0.587 * patch[:, :, 1].astype(np.float32) + 0.299 * patch[:, :, 2].astype(np.float32)
            dark_fraction = float((luma <= self.dark_luma_threshold).mean())
            if dark_fraction >= self.dark_fraction_threshold:
                dark_corners += 1

        dark_now = dark_corners >= 3
        if dark_now:
            self._dark_streak += 1
            self._bright_streak = 0
            if self._dark_streak >= self.engage_required:
                self._scoped = True
        else:
            self._bright_streak += 1
            self._dark_streak = 0
            if self._bright_streak >= self.release_required:
                self._scoped = False
        return self._scoped


class XAxisPredictor:
    def __init__(self) -> None:
        self._history: dict[str, deque[tuple[float, float]]] = {}

    def reset(self, name: str) -> None:
        self._history.pop(name, None)

    def reset_many(self, names) -> None:
        for name in names:
            self._history.pop(name, None)

    def predict(
        self,
        name: str,
        observed_x: float,
        now: float,
        *,
        enabled: bool,
        history_ms: float,
        min_samples: int,
        lead_ms: float,
        damping: float,
        max_delta_px: float,
        reset_distance_px: float,
    ) -> float:
        if not enabled:
            self.reset(name)
            return float(observed_x)

        hist = self._history.setdefault(name, deque())
        obs = float(observed_x)
        if hist and abs(obs - hist[-1][1]) >= max(1.0, float(reset_distance_px)):
            hist.clear()

        hist.append((float(now), obs))
        window_s = max(0.03, float(history_ms) / 1000.0)
        while hist and (now - hist[0][0]) > window_s:
            hist.popleft()

        if len(hist) < max(2, int(min_samples)):
            return obs

        ts = np.array([t for t, _ in hist], dtype=np.float64)
        xs = np.array([x for _, x in hist], dtype=np.float64)
        ts = ts - ts.mean()
        xs_mean = float(xs.mean())
        denom = float(np.dot(ts, ts))
        if denom <= 1e-9:
            return obs

        slope = float(np.dot(ts, xs - xs_mean) / denom)
        pred_dt = max(0.0, float(lead_ms)) / 1000.0
        predicted = obs + slope * pred_dt

        max_delta = max(0.0, float(max_delta_px))
        delta = max(-max_delta, min(max_delta, predicted - obs))

        damping = max(0.0, min(1.0, float(damping)))
        blend = 1.0 - damping
        return obs + delta * blend
