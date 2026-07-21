from __future__ import annotations

import unittest

from app.components.cv_trigger.roi import CaptureRegion, compute_center_roi
from app.components.cv_trigger.core import _capture_region_for_config


class CVTriggerRoiTests(unittest.TestCase):
    def test_center_roi_uses_absolute_capture_and_monitor_local_translation(self) -> None:
        region = compute_center_roi(
            monitor={"left": 100, "top": 200, "width": 1000, "height": 800},
            max_snap_distance=100,
            inference_img_size=256,
            roi_padding_px=50,
        )

        self.assertEqual(region.roi_left, 350)
        self.assertEqual(region.roi_top, 250)
        self.assertEqual(region.as_capture_dict(), {"left": 450, "top": 450, "width": 300, "height": 300})
        self.assertEqual(region.translate_box((10, 20, 30, 40)), (360, 270, 380, 290))

    def test_roi_minimum_side_is_inference_image_size(self) -> None:
        region = compute_center_roi(
            monitor={"left": 0, "top": 0, "width": 2560, "height": 1440},
            max_snap_distance=25,
            inference_img_size=512,
            roi_padding_px=10,
        )

        self.assertEqual(region.width, 512)
        self.assertEqual(region.height, 512)

    def test_roi_clamps_to_monitor_bounds(self) -> None:
        region = compute_center_roi(
            monitor={"left": 10, "top": 20, "width": 300, "height": 200},
            max_snap_distance=500,
            inference_img_size=512,
            roi_padding_px=100,
        )

        self.assertEqual(region, CaptureRegion(monitor_left=10, monitor_top=20, roi_left=0, roi_top=0, width=300, height=200))
        self.assertEqual(region.as_capture_dict(), {"left": 10, "top": 20, "width": 300, "height": 200})

    def test_auto_capture_uses_roi_when_visual_scope_rule_exists(self) -> None:
        region = _capture_region_for_config(
            monitor={"left": 10, "top": 20, "width": 2560, "height": 1440},
            enabled_configs={"scout": {"only_when_scoped_visual": True, "SNAP_DISTANCE": 80}},
            inference_img_size=256,
            config={"capture_mode": "auto", "roi_padding_px": 50},
        )

        self.assertLess(region.width, 2560)
        self.assertEqual(region.width, 260)

    def test_full_capture_mode_uses_full_frame(self) -> None:
        region = _capture_region_for_config(
            monitor={"left": 10, "top": 20, "width": 300, "height": 200},
            enabled_configs={"scout": {"only_when_scoped_visual": True, "SNAP_DISTANCE": 80}},
            inference_img_size=256,
            config={"capture_mode": "full"},
        )

        self.assertEqual(region, CaptureRegion(monitor_left=10, monitor_top=20, roi_left=0, roi_top=0, width=300, height=200))

    def test_auto_capture_uses_roi_without_visual_scope_rule(self) -> None:
        region = _capture_region_for_config(
            monitor={"left": 0, "top": 0, "width": 2560, "height": 1440},
            enabled_configs={"rifle": {"only_when_scoped_visual": False, "SNAP_DISTANCE": 100}},
            inference_img_size=256,
            config={"capture_mode": "auto", "roi_padding_px": 50},
        )

        self.assertLess(region.width, 2560)
        self.assertEqual(region.width, 300)


if __name__ == "__main__":
    _ = unittest.main()
