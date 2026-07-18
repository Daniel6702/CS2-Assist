from __future__ import annotations

import numpy as np


class PositionSmoother:
    """Exponential moving average per rule to dampen YOLO bounding-box jitter.

    Each rule gets its own EMA state keyed by ``name``.  An ``alpha`` near
    0.0 smooths heavily (slow to respond), near 1.0 barely smooths at all.
    The default ``alpha=0.5`` (window≈3 frames) is a good balance for 60 fps
    capture against CS2-width strafing speeds.
    """

    def __init__(self, alpha: float = 0.50) -> None:
        self._state: dict[str, tuple[float, float] | None] = {}
        self.alpha = max(0.0, min(1.0, float(alpha)))

    def reset(self, name: str) -> None:
        self._state.pop(name, None)

    def reset_many(self, names) -> None:
        for name in names:
            self._state.pop(name, None)

    def smooth(self, name: str, x: float, y: float) -> tuple[float, float]:
        """Return ``(smoothed_x, smoothed_y)`` for *name*."""
        prev = self._state.get(name)
        if prev is None:
            self._state[name] = (float(x), float(y))
            return (float(x), float(y))
        a = self.alpha
        sx = prev[0] + a * (float(x) - prev[0])
        sy = prev[1] + a * (float(y) - prev[1])
        self._state[name] = (sx, sy)
        return (sx, sy)


class ScopeDetector:
    """Detects whether the player is scoped based on dark corner patches."""

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



