from __future__ import annotations

import os
import sys
import unittest

from tests.optional_dependency_stubs import install_mss_stub, install_pynput_stub

install_mss_stub()
install_pynput_stub()

_ = os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6 import QtWidgets  # noqa: E402
except ImportError:
    QtWidgets = None

app = None if QtWidgets is None else QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from app.defaults import default_profile  # noqa: E402
from app.gsi import GameState  # noqa: E402
from app.gsi_state import GameState as ParsedGameState  # noqa: E402
from app.runtime import RuntimeManager  # noqa: E402

if QtWidgets is not None:
    from app.ui.tabs.misc_tab import MiscTab  # noqa: E402


def _state(round_phase: str | None) -> GameState:
    return GameState(
        raw={},
        current_weapon=None,
        ammo_clip=None,
        ammo_clip_max=None,
        player_alive=True,
        round_phase=round_phase,
        map_name="de_dust2",
        features_allowed=True,
        kills=0,
        team="T",
        defusekit=False,
        is_scoped=None,
        flashed=False,
    )


class RoundStartAlertComponentTests(unittest.TestCase):
    def test_plays_once_when_round_phase_changes_from_freezetime_to_live(self) -> None:
        from app.components.round_start_alert import RoundStartAlertComponent

        played: list[tuple[str, int]] = []
        component = RoundStartAlertComponent(sound_player=lambda path, volume: played.append((path, volume)))
        component.configure({"enabled": True, "sound_file": "/tmp/round.wav", "volume": 65})
        component.start()

        component.on_gsi_state(_state("freezetime"))
        component.on_gsi_state(_state("live"))
        component.on_gsi_state(_state("live"))

        self.assertEqual(played, [("/tmp/round.wav", 65)])

    def test_does_not_play_without_freezetime_to_live_transition(self) -> None:
        from app.components.round_start_alert import RoundStartAlertComponent

        played: list[tuple[str, int]] = []
        component = RoundStartAlertComponent(sound_player=lambda path, volume: played.append((path, volume)))
        component.configure({"enabled": True, "sound_file": "/tmp/round.wav", "volume": 50})
        component.start()

        component.on_gsi_state(_state("warmup"))
        component.on_gsi_state(_state("live"))

        self.assertEqual(played, [])

    def test_gsi_payload_round_phase_reads_round_then_phase_countdowns(self) -> None:
        self.assertEqual(ParsedGameState.from_payload({"round": {"phase": "freezetime"}}).round_phase, "freezetime")
        self.assertEqual(ParsedGameState.from_payload({"phase_countdowns": {"phase": "live"}}).round_phase, "live")


class RoundStartAlertWiringTests(unittest.TestCase):
    def test_runtime_registers_round_start_alert_component(self) -> None:
        from app.components.round_start_alert import RoundStartAlertComponent

        runtime = RuntimeManager(status_callback=lambda _source, _message: None)

        self.assertIn("round_start_alert", runtime.components)
        self.assertIsInstance(runtime.components["round_start_alert"], RoundStartAlertComponent)

    def test_default_profile_contains_disabled_round_start_alert_section(self) -> None:
        profile = default_profile()

        self.assertEqual(profile["components"]["round_start_alert"], {"enabled": False, "sound_file": "", "volume": 50})

    def test_misc_tab_round_trips_round_start_alert_config(self) -> None:
        if QtWidgets is None:
            self.skipTest("PySide6 is unavailable")
        tab = MiscTab()
        try:
            tab.load_config("round_start_alert", {"enabled": True, "sound_file": "/tmp/round.wav", "volume": 42})

            extracted = tab.extract_config()["round_start_alert"]
        finally:
            tab.close()
            tab.deleteLater()
            app.processEvents()

        self.assertEqual(extracted, {"enabled": True, "sound_file": "/tmp/round.wav", "volume": 42})


if __name__ == "__main__":
    _ = unittest.main()
