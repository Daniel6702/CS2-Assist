from __future__ import annotations

import os
import sys
import unittest
from collections.abc import Callable

from tests.optional_dependency_stubs import install_mss_stub, install_pynput_stub

install_mss_stub()
install_pynput_stub()

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6 import QtCore, QtWidgets  # noqa: E402
except ImportError:
    QtCore = None
    QtWidgets = None

app = None if QtWidgets is None else QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from app.components.sniper_crosshair import SNIPER_CROSSHAIR_STRETCH_FILTER, SniperCrosshairComponent  # noqa: E402
from app.components.pixel_trigger import ScopePixelState  # noqa: E402
from app.defaults import default_profile  # noqa: E402
from app.gsi import GameState  # noqa: E402
from app.runtime import RuntimeManager  # noqa: E402
from app.ui.widgets.crosshair_codec import CS2CrosshairCodec  # noqa: E402

if QtWidgets is not None:
    from app.ui.tabs.misc_tab import MiscTab  # noqa: E402
    from app.ui.widgets.sniper_crosshair_overlay import SniperCrosshairOverlay  # noqa: E402


def _state(weapon: str | None, scoped: bool | None) -> GameState:
    return GameState(
        raw={},
        current_weapon=weapon,
        ammo_clip=10,
        ammo_clip_max=10,
        player_alive=True,
        round_phase="live",
        map_name="de_dust2",
        features_allowed=True,
        kills=0,
        team="T",
        defusekit=False,
        is_scoped=scoped,
        flashed=False,
    )


class SniperCrosshairComponentTests(unittest.TestCase):
    def test_visible_when_existing_scope_provider_reports_unscoped_and_awp_or_ssg08(self) -> None:
        component = SniperCrosshairComponent()
        component.configure(
            {
                "enabled": True,
                "crosshair_code": "CSGO-abcde-abcde-abcde-abcde-abcde",
                "scope_state_provider": lambda: False,
            },
        )
        component.start()

        component.on_gsi_state(_state("weapon_awp", True))
        awp_state = component.overlay_state()
        component.on_gsi_state(_state("weapon_ssg08", True))
        scout_state = component.overlay_state()

        self.assertTrue(awp_state.visible)
        self.assertTrue(scout_state.visible)
        self.assertEqual(awp_state.crosshair_code, "CSGO-abcde-abcde-abcde-abcde-abcde")

    def test_hidden_when_existing_scope_provider_reports_scoped_unknown_disabled_or_non_sniper(self) -> None:
        scope_state = True

        def scope_state_provider() -> bool | None:
            return scope_state

        component = SniperCrosshairComponent()
        component.configure({"enabled": True, "scope_state_provider": scope_state_provider})
        component.start()

        component.on_gsi_state(_state("weapon_awp", False))
        scoped_state = component.overlay_state()
        scope_state = None
        component.on_gsi_state(_state("weapon_awp", False))
        unknown_state = component.overlay_state()
        scope_state = False
        component.on_gsi_state(_state("weapon_ak47", False))
        rifle_state = component.overlay_state()
        component.stop()
        component.on_gsi_state(_state("weapon_awp", False))
        stopped_state = component.overlay_state()

        self.assertFalse(scoped_state.visible)
        self.assertFalse(unknown_state.visible)
        self.assertFalse(rifle_state.visible)
        self.assertFalse(stopped_state.visible)

    def test_stay_when_scoped_keeps_visible_for_scoped_sniper_only(self) -> None:
        component = SniperCrosshairComponent()
        component.configure({"enabled": True, "stay_when_scoped": True, "scope_state_provider": lambda: True})
        component.start()

        component.on_gsi_state(_state("weapon_awp", False))
        scoped_sniper_state = component.overlay_state()
        component.on_gsi_state(_state("weapon_ak47", False))
        scoped_rifle_state = component.overlay_state()

        self.assertTrue(scoped_sniper_state.visible)
        self.assertFalse(scoped_rifle_state.visible)

    def test_gsi_scoped_field_does_not_drive_visibility(self) -> None:
        component = SniperCrosshairComponent()
        component.configure({"enabled": True, "scope_state_provider": lambda: None})
        component.start()

        component.on_gsi_state(_state("weapon_awp", False))

        self.assertFalse(component.overlay_state().visible)

    def test_stretched_overlay_uses_pixel_trigger_linear_filter(self) -> None:
        self.assertEqual(SNIPER_CROSSHAIR_STRETCH_FILTER, "linear")


class SniperCrosshairWiringTests(unittest.TestCase):
    def test_runtime_registers_component_and_injects_pixel_trigger_crosshair_code(self) -> None:
        runtime = RuntimeManager(status_callback=lambda _source, _message: None)
        profile = default_profile()
        profile["components"]["pixel_trigger"]["crosshair_code"] = "CSGO-abcde-abcde-abcde-abcde-abcde"

        runtime.configure_all(profile)

        self.assertIn("sniper_crosshair", runtime.components)
        self.assertIsInstance(runtime.components["sniper_crosshair"], SniperCrosshairComponent)
        self.assertEqual(
            runtime.components["sniper_crosshair"].config["crosshair_code"],
            "CSGO-abcde-abcde-abcde-abcde-abcde",
        )

    def test_runtime_prefers_sniper_crosshair_code_over_pixel_trigger_code(self) -> None:
        runtime = RuntimeManager(status_callback=lambda _source, _message: None)
        pixel_code = "CSGO-abcde-abcde-abcde-abcde-abcde"
        sniper_code = CS2CrosshairCodec().generate_code(CS2CrosshairCodec.DEFAULT_SETTINGS)
        profile = default_profile()
        profile["components"]["pixel_trigger"]["crosshair_code"] = pixel_code
        profile["components"]["sniper_crosshair"]["crosshair_code"] = sniper_code

        runtime.configure_all(profile)

        self.assertEqual(runtime.components["sniper_crosshair"].config["crosshair_code"], sniper_code)

    def test_runtime_injects_existing_pixel_trigger_scope_state_provider(self) -> None:
        runtime = RuntimeManager(status_callback=lambda _source, _message: None)
        profile = default_profile()

        runtime.configure_all(profile)
        provider = runtime.components["sniper_crosshair"].config["scope_state_provider"]
        runtime.components["pixel_trigger"]._set_scope_state(ScopePixelState(is_scoped=False))

        self.assertIsInstance(provider, Callable)
        self.assertFalse(provider())

    def test_runtime_starts_pixel_trigger_for_scope_tracking_when_sniper_crosshair_enabled(self) -> None:
        runtime = RuntimeManager(status_callback=lambda _source, _message: None)
        profile = default_profile()
        profile["components"]["pixel_trigger"]["enabled"] = False
        profile["components"]["sniper_crosshair"]["enabled"] = True

        runtime.configure_all(profile)
        runtime.apply_enabled_states(profile)
        try:
            self.assertTrue(runtime.components["pixel_trigger"].enabled)
            self.assertFalse(runtime.components["pixel_trigger"].config["enabled"])
            self.assertTrue(runtime.components["pixel_trigger"].config["scope_tracking_enabled"])
        finally:
            runtime.stop_all()

    def test_default_profile_contains_disabled_sniper_crosshair_section(self) -> None:
        profile = default_profile()

        self.assertEqual(
            profile["components"]["sniper_crosshair"],
            {"enabled": False, "crosshair_code": "", "stay_when_scoped": False},
        )

    def test_misc_tab_round_trips_sniper_crosshair_config(self) -> None:
        if QtWidgets is None:
            self.skipTest("PySide6 is unavailable")
        tab = MiscTab()
        try:
            tab.load_config("sniper_crosshair", {"enabled": True})

            extracted = tab.extract_config()["sniper_crosshair"]
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()

        self.assertEqual(extracted, {"enabled": True, "crosshair_code": "", "stay_when_scoped": False})

    def test_misc_tab_round_trips_stay_when_scoped(self) -> None:
        if QtWidgets is None:
            self.skipTest("PySide6 is unavailable")
        tab = MiscTab()
        try:
            tab.load_config("sniper_crosshair", {"enabled": True, "stay_when_scoped": True})

            extracted = tab.extract_config()["sniper_crosshair"]
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()

        self.assertTrue(extracted["stay_when_scoped"])

    def test_misc_tab_round_trips_sniper_crosshair_code(self) -> None:
        if QtWidgets is None:
            self.skipTest("PySide6 is unavailable")
        sniper_code = CS2CrosshairCodec().generate_code(CS2CrosshairCodec.DEFAULT_SETTINGS)
        tab = MiscTab()
        try:
            tab.load_config("sniper_crosshair", {"enabled": True, "crosshair_code": sniper_code})

            extracted = tab.extract_config()["sniper_crosshair"]
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()

        self.assertEqual(extracted, {"enabled": True, "crosshair_code": sniper_code, "stay_when_scoped": False})

    def test_overlay_uses_translucent_input_transparent_window(self) -> None:
        if QtWidgets is None or QtCore is None:
            self.skipTest("PySide6 is unavailable")
        overlay = SniperCrosshairOverlay()
        try:
            flags = overlay.windowFlags()

            self.assertTrue(overlay.testAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground))
            self.assertTrue(bool(flags & QtCore.Qt.WindowType.WindowTransparentForInput))
            self.assertTrue(bool(flags & QtCore.Qt.WindowType.FramelessWindowHint))
        finally:
            overlay.hide_overlay()
            overlay.close()
            overlay.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    _ = unittest.main()
