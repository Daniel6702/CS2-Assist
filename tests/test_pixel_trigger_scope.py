from __future__ import annotations

import os
import sys
import unittest

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from app.components.pixel_trigger import (  # noqa: E402
    MonitorOrigin,
    PixelCoordinates,
    PixelTriggerComponent,
    PixelMonitorSelection,
    ScopeBlurConfig,
    ScopePixelState,
    update_scope_blur_state,
)
from app.device_service import DeviceService  # noqa: E402
from app.ui.tabs.pixel_trigger_tab import PixelTriggerTab  # noqa: E402


class PixelTriggerScopeTests(unittest.TestCase):
    def test_pixel_trigger_tab_uses_one_to_three_page_split(self) -> None:
        tab = PixelTriggerTab(DeviceService())
        scroll = tab.findChild(QtWidgets.QScrollArea)
        self.assertIsNotNone(scroll)

        content = scroll.widget()
        columns = content.layout()

        self.assertEqual(columns.stretch(0), 1)
        self.assertEqual(columns.stretch(1), 3)

    def test_crosshair_code_toolbar_has_no_copy_button(self) -> None:
        tab = PixelTriggerTab(DeviceService())

        button_labels = {button.text() for button in tab.findChildren(QtWidgets.QPushButton)}

        self.assertNotIn("Copy", button_labels)

    def test_base_and_scope_pixel_selectors_are_side_by_side(self) -> None:
        tab = PixelTriggerTab(DeviceService())
        selection_row = tab.findChild(QtWidgets.QWidget, "pixel_selection_row")
        self.assertIsNotNone(selection_row)

        layout = selection_row.layout()

        self.assertIsInstance(layout, QtWidgets.QGridLayout)
        self.assertIsNotNone(layout.itemAtPosition(0, 0))
        self.assertIsNotNone(layout.itemAtPosition(0, 1))
        self.assertIsNotNone(layout.itemAtPosition(1, 0))
        self.assertIsNotNone(layout.itemAtPosition(1, 1))
        self.assertIsNotNone(layout.itemAtPosition(2, 0))
        self.assertIsNotNone(layout.itemAtPosition(2, 1))
        self.assertIsNotNone(layout.itemAtPosition(3, 0))
        self.assertIsNotNone(layout.itemAtPosition(3, 1))
        self.assertIsNone(layout.itemAtPosition(4, 0))
        self.assertIsNotNone(layout.itemAtPosition(4, 1))

    def test_sniper_scope_grid_is_twelve_by_twelve(self) -> None:
        tab = PixelTriggerTab(DeviceService())

        self.assertEqual(tab._scope_grid.image_dimensions(), (12, 12))

    def test_scope_state_selects_scope_pixel_coordinates(self) -> None:
        selection = PixelMonitorSelection(
            origin=MonitorOrigin(left=100, top=200),
            base=PixelCoordinates(x=10, y=20),
            scope=PixelCoordinates(x=30, y=40),
            blur=ScopeBlurConfig(offset_x=0, offset_y=0, duration_ms=0),
        )

        self.assertEqual(selection.resolve(ScopePixelState(is_scoped=True)), (130, 240))
        self.assertEqual(selection.resolve(ScopePixelState(is_scoped=False)), (110, 220))
        self.assertEqual(selection.resolve(ScopePixelState(is_scoped=None)), (110, 220))

    def test_scope_blur_offset_applies_only_during_configured_window(self) -> None:
        selection = PixelMonitorSelection(
            origin=MonitorOrigin(left=100, top=200),
            base=PixelCoordinates(x=10, y=20),
            scope=PixelCoordinates(x=30, y=40),
            blur=ScopeBlurConfig(offset_x=-6, offset_y=-8, duration_ms=150),
        )

        active = ScopePixelState(is_scoped=True, blur_until=1.15)
        expired = ScopePixelState(is_scoped=True, blur_until=1.15)

        self.assertEqual(selection.resolve(active, now=1.10), (124, 232))
        self.assertEqual(selection.resolve(expired, now=1.16), (130, 240))

    def test_scope_blur_window_starts_only_on_scope_in_transition(self) -> None:
        previous = ScopePixelState(is_scoped=False)

        scoped = update_scope_blur_state(previous, detected_scoped=True, now=10.0, duration_ms=125)
        still_scoped = update_scope_blur_state(scoped, detected_scoped=True, now=10.02, duration_ms=125)
        unscoped = update_scope_blur_state(still_scoped, detected_scoped=False, now=10.03, duration_ms=125)

        self.assertEqual(scoped.blur_until, 10.125)
        self.assertEqual(still_scoped.blur_until, 10.125)
        self.assertEqual(unscoped.blur_until, 0.0)

    def test_gsi_scoped_field_does_not_drive_pixel_trigger_scope_state(self) -> None:
        component = PixelTriggerComponent()

        class GsiState:
            is_scoped = True

        component.on_gsi_state(GsiState())

        self.assertIsNone(component.scope_state())

    def test_scope_blur_settings_round_trip_from_pixel_trigger_tab(self) -> None:
        tab = PixelTriggerTab(DeviceService())
        tab.load_config(
            {
                "scope_blur_offset_x": -6,
                "scope_blur_offset_y": -8,
                "scope_blur_duration_ms": 150,
            },
        )

        extracted = tab.extract_config()

        self.assertEqual(extracted["scope_blur_offset_x"], -6)
        self.assertEqual(extracted["scope_blur_offset_y"], -8)
        self.assertEqual(extracted["scope_blur_duration_ms"], 150)

    def test_resolution_settings_are_loaded_but_not_extracted(self) -> None:
        tab = PixelTriggerTab(DeviceService())
        tab.load_config(
            {
                "game_resolution": {"width": 1600, "height": 1200},
                "display_resolution": {"width": 2560, "height": 1440},
                "game_resolution_stretched": True,
            },
        )

        extracted = tab.extract_config()

        self.assertEqual(tab._target_frame_dimensions(), (2560, 1440))
        self.assertNotIn("game_resolution", extracted)
        self.assertNotIn("display_resolution", extracted)
        self.assertNotIn("stretched", extracted)
        self.assertNotIn("game_resolution_stretched", extracted)


if __name__ == "__main__":
    _ = unittest.main()
