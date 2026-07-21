from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class CaptureRegion:
    monitor_left: int
    monitor_top: int
    roi_left: int
    roi_top: int
    width: int
    height: int

    def as_capture_dict(self) -> dict[str, int]:
        return {
            "left": self.monitor_left + self.roi_left,
            "top": self.monitor_top + self.roi_top,
            "width": self.width,
            "height": self.height,
        }

    def translate_box(self, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = box
        return (
            x1 + self.roi_left,
            y1 + self.roi_top,
            x2 + self.roi_left,
            y2 + self.roi_top,
        )


def compute_center_roi(
    *,
    monitor: Mapping[str, int],
    max_snap_distance: int,
    inference_img_size: int,
    roi_padding_px: int,
    roi_min_size_px: int = 0,
    roi_max_size_px: int | None = None,
) -> CaptureRegion:
    monitor_left = int(monitor.get("left", 0))
    monitor_top = int(monitor.get("top", 0))
    monitor_width = max(1, int(monitor.get("width", 1)))
    monitor_height = max(1, int(monitor.get("height", 1)))

    half_extent = max(
        float(max(0, max_snap_distance) + max(0, roi_padding_px)),
        max(1.0, float(inference_img_size) / 2.0),
        max(0.0, float(roi_min_size_px) / 2.0),
    )
    side = int(math.ceil(half_extent * 2.0))
    if roi_max_size_px is not None and roi_max_size_px > 0:
        side = min(side, int(roi_max_size_px))

    roi_width = min(monitor_width, max(1, side))
    roi_height = min(monitor_height, max(1, side))
    center_x = monitor_width // 2
    center_y = monitor_height // 2
    roi_left = min(max(0, center_x - (roi_width // 2)), monitor_width - roi_width)
    roi_top = min(max(0, center_y - (roi_height // 2)), monitor_height - roi_height)

    return CaptureRegion(
        monitor_left=monitor_left,
        monitor_top=monitor_top,
        roi_left=roi_left,
        roi_top=roi_top,
        width=roi_width,
        height=roi_height,
    )
