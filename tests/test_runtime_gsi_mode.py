from __future__ import annotations

import unittest

from tests.optional_dependency_stubs import install_mss_stub, install_pynput_stub

install_mss_stub()
install_pynput_stub()

from app.components.base import BaseComponent
from app.gsi import GameState
from app.runtime import RuntimeManager


class RuntimeGSIModeTests(unittest.TestCase):
    def test_on_mode_forces_system_active(self) -> None:
        statuses: list[tuple[str, str]] = []
        runtime = RuntimeManager(status_callback=lambda source, message: statuses.append((source, message)))
        probe = BaseComponent()
        runtime.components = {"probe": probe}

        runtime.configure_gsi({"mode": "on", "host": "127.0.0.1", "port": 0})
        try:
            self.assertTrue(probe.runtime_gate_open())
            self.assertEqual(probe.runtime_gate_reason(), "")
            self.assertIn(("gsi_shutoff", "Active"), statuses)
        finally:
            runtime.stop_all()

    def test_off_mode_forces_system_inactive(self) -> None:
        statuses: list[tuple[str, str]] = []
        runtime = RuntimeManager(status_callback=lambda source, message: statuses.append((source, message)))
        probe = BaseComponent()
        runtime.components = {"probe": probe}

        runtime.configure_gsi({"mode": "off", "host": "127.0.0.1", "port": 0})
        try:
            self.assertFalse(probe.runtime_gate_open())
            self.assertEqual(probe.runtime_gate_reason(), "manual_off")
            self.assertIn(("gsi_shutoff", "Inactive"), statuses)
        finally:
            runtime.stop_all()

    def test_gsi_mode_follows_gsi_state(self) -> None:
        statuses: list[tuple[str, str]] = []
        runtime = RuntimeManager(status_callback=lambda source, message: statuses.append((source, message)))
        probe = BaseComponent()
        runtime.components = {"probe": probe}
        runtime.configure_gsi({"mode": "gsi", "host": "127.0.0.1", "port": 0})

        try:
            runtime.on_gsi_state(
                GameState(
                    raw={},
                    current_weapon=None,
                    ammo_clip=None,
                    ammo_clip_max=None,
                    player_alive=True,
                    round_phase="live",
                    map_name=None,
                    features_allowed=True,
                    kills=None,
                    team=None,
                    defusekit=None,
                    is_scoped=None,
                    flashed=None,
                    local_status="Alive",
                    shutoff_reason="",
                ),
            )
            self.assertTrue(probe.runtime_gate_open())
            self.assertIn(("gsi_shutoff", "Active"), statuses)
        finally:
            runtime.stop_all()


if __name__ == "__main__":
    _ = unittest.main()
