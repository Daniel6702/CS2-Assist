from __future__ import annotations

OBSCURED_MOUSE_NAME = "HID-compliant mouse"
OBSCURED_KEYBOARD_NAME = "HID-compliant keyboard"

ORIGINAL_CV_MOUSE_NAME = "cs2-unified-cv-trigger-mouse"
ORIGINAL_RECOIL_MOUSE_NAME = "cs2-unified-recoil-virtual-mouse"


def device_name(_original: str) -> str:
    return OBSCURED_MOUSE_NAME
