from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch

from app.components.cv_trigger.postprocess import extract_filtered_detections


@dataclass(frozen=True, slots=True)
class FakeBoxes:
    xyxy: Any
    cls: Any


class CVTriggerPostprocessTests(unittest.TestCase):
    def test_filters_torch_boxes_before_cpu_translation(self) -> None:
        boxes = FakeBoxes(
            xyxy=torch.tensor(
                [
                    [10.0, 20.0, 30.0, 40.0],
                    [50.0, 60.0, 70.0, 80.0],
                    [90.0, 100.0, 110.0, 120.0],
                ]
            ),
            cls=torch.tensor([1.0, 2.0, 3.0]),
        )

        extracted = extract_filtered_detections(
            boxes=boxes,
            target_class_ids={2, 3},
            roi_left=5,
            roi_top=7,
        )

        self.assertEqual(extracted.source_count, 3)
        self.assertEqual(extracted.selected_count, 2)
        np.testing.assert_allclose(
            extracted.boxes_xyxy,
            np.array([[55.0, 67.0, 75.0, 87.0], [95.0, 107.0, 115.0, 127.0]]),
        )
        np.testing.assert_allclose(extracted.boxes_cls, np.array([2.0, 3.0]))

    def test_filters_numpy_boxes_with_same_result(self) -> None:
        boxes = FakeBoxes(
            xyxy=np.array(
                [
                    [10.0, 20.0, 30.0, 40.0],
                    [50.0, 60.0, 70.0, 80.0],
                    [90.0, 100.0, 110.0, 120.0],
                ]
            ),
            cls=np.array([1.0, 2.0, 3.0]),
        )

        extracted = extract_filtered_detections(
            boxes=boxes,
            target_class_ids={2, 3},
            roi_left=5,
            roi_top=7,
        )

        self.assertEqual(extracted.source_count, 3)
        self.assertEqual(extracted.selected_count, 2)
        np.testing.assert_allclose(
            extracted.boxes_xyxy,
            np.array([[55.0, 67.0, 75.0, 87.0], [95.0, 107.0, 115.0, 127.0]]),
        )
        np.testing.assert_allclose(extracted.boxes_cls, np.array([2.0, 3.0]))

    def test_empty_target_classes_skip_all_boxes(self) -> None:
        boxes = FakeBoxes(
            xyxy=torch.tensor([[10.0, 20.0, 30.0, 40.0]]),
            cls=torch.tensor([1.0]),
        )

        extracted = extract_filtered_detections(boxes=boxes, target_class_ids=set())

        self.assertEqual(extracted.selected_count, 0)
        self.assertEqual(extracted.boxes_xyxy, [])


if __name__ == "__main__":
    _ = unittest.main()
