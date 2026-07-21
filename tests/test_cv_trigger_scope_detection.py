from __future__ import annotations

import unittest

import numpy as np

from app.components.cv_trigger.detection import ScopeDetector, scope_corner_capture_regions, scope_corner_patches


def _dark_frame() -> np.ndarray:
    frame = np.full((100, 120, 3), 80, dtype=np.uint8)
    p = 24
    frame[0:p, 0:p] = 0
    frame[0:p, -p:] = 0
    frame[-p:, 0:p] = 0
    frame[-p:, -p:] = 0
    return frame


def _corner_patches(frame: np.ndarray) -> list[np.ndarray]:
    return list(scope_corner_patches(frame, 24))


class ScopeDetectorTests(unittest.TestCase):
    def test_corner_patches_match_full_frame_scope_engage(self) -> None:
        frame = _dark_frame()
        full = ScopeDetector(engage_required=1)
        patches = ScopeDetector(engage_required=1)

        self.assertEqual(full.update(frame), patches.update_patches(_corner_patches(frame)))

    def test_corner_patches_match_full_frame_scope_release(self) -> None:
        dark = _dark_frame()
        bright = np.full((100, 120, 3), 80, dtype=np.uint8)
        full = ScopeDetector(engage_required=1, release_required=1)
        patches = ScopeDetector(engage_required=1, release_required=1)

        self.assertTrue(full.update(dark))
        self.assertTrue(patches.update_patches(_corner_patches(dark)))
        self.assertEqual(full.update(bright), patches.update_patches(_corner_patches(bright)))

    def test_corner_capture_regions_use_monitor_corners(self) -> None:
        regions = scope_corner_capture_regions({"left": 100, "top": 200, "width": 300, "height": 240}, 24)

        self.assertEqual(
            regions,
            (
                {"left": 100, "top": 200, "width": 24, "height": 24},
                {"left": 376, "top": 200, "width": 24, "height": 24},
                {"left": 100, "top": 416, "width": 24, "height": 24},
                {"left": 376, "top": 416, "width": 24, "height": 24},
            ),
        )


if __name__ == "__main__":
    _ = unittest.main()
