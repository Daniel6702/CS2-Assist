from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class ExtractedDetections:
    boxes_xyxy: Any
    boxes_cls: Any
    source_count: int
    selected_count: int


def _empty_detections(source_count: int = 0) -> ExtractedDetections:
    return ExtractedDetections(boxes_xyxy=[], boxes_cls=[], source_count=source_count, selected_count=0)


def _to_numpy(value: Any) -> Any:
    cpu = getattr(value, "cpu", None)
    if callable(cpu):
        return cpu().numpy()
    return np.asarray(value)


def _filter_with_torch(boxes_xyxy: Any, boxes_cls: Any, target_class_ids: set[int]) -> tuple[Any, Any]:
    import torch

    class_ids = torch.as_tensor(sorted(target_class_ids), device=boxes_cls.device, dtype=boxes_cls.dtype)
    mask = (boxes_cls[:, None] == class_ids).any(dim=1)
    return boxes_xyxy[mask].clone(), boxes_cls[mask].clone()


def _filter_with_numpy(boxes_xyxy: Any, boxes_cls: Any, target_class_ids: set[int]) -> tuple[Any, Any]:
    cls_array = np.asarray(boxes_cls)
    mask = np.isin(cls_array.astype(int), list(target_class_ids))
    return np.asarray(boxes_xyxy)[mask].copy(), cls_array[mask].copy()


def extract_filtered_detections(
    *,
    boxes: Any,
    target_class_ids: set[int],
    roi_left: int = 0,
    roi_top: int = 0,
) -> ExtractedDetections:
    if boxes is None or not target_class_ids:
        return _empty_detections()

    boxes_xyxy = boxes.xyxy
    boxes_cls = boxes.cls
    source_count = len(boxes_cls)
    if source_count == 0:
        return _empty_detections(source_count)

    try:
        filtered_xyxy, filtered_cls = _filter_with_torch(boxes_xyxy, boxes_cls, target_class_ids)
    except (AttributeError, ImportError, TypeError):
        filtered_xyxy, filtered_cls = _filter_with_numpy(boxes_xyxy, boxes_cls, target_class_ids)

    selected_count = len(filtered_cls)
    if selected_count == 0:
        return _empty_detections(source_count)

    xyxy_array = _to_numpy(filtered_xyxy)
    cls_array = _to_numpy(filtered_cls)
    if roi_left or roi_top:
        xyxy_array[:, [0, 2]] += roi_left
        xyxy_array[:, [1, 3]] += roi_top
    return ExtractedDetections(
        boxes_xyxy=xyxy_array,
        boxes_cls=cls_array,
        source_count=source_count,
        selected_count=selected_count,
    )
