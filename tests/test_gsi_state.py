from __future__ import annotations

import unittest

from app.gsi import GSIStateTracker


def _payload(
    *,
    phase: str | None,
    health: int | str | None,
    provider_steamid: str = "76561198000000001",
    player_steamid: str = "76561198000000001",
) -> dict:
    player_state = {} if health is None else {"health": health}
    return {
        "provider": {"steamid": provider_steamid},
        "player": {
            "steamid": player_steamid,
            "state": player_state,
            "weapons": {},
        },
        "round": {"phase": phase},
    }


class GSIStateTrackerTests(unittest.TestCase):
    def test_shutoff_active_when_round_is_not_live(self) -> None:
        tracker = GSIStateTracker()

        state = tracker.state_from_payload(_payload(phase="freezetime", health=100))

        self.assertFalse(state.features_allowed)
        self.assertEqual(state.local_status, "Not live")
        self.assertEqual(state.shutoff_reason, "round_not_live")

    def test_shutoff_inactive_when_local_player_is_alive_in_live_round(self) -> None:
        tracker = GSIStateTracker()

        state = tracker.state_from_payload(_payload(phase="live", health=100))

        self.assertTrue(state.features_allowed)
        self.assertEqual(state.local_status, "Alive")
        self.assertEqual(state.shutoff_reason, "")

    def test_shutoff_active_when_local_player_is_dead_in_live_round(self) -> None:
        tracker = GSIStateTracker()

        state = tracker.state_from_payload(_payload(phase="live", health=0))

        self.assertFalse(state.features_allowed)
        self.assertEqual(state.local_status, "Dead")
        self.assertEqual(state.shutoff_reason, "player_dead")

    def test_steamid_change_latches_death_while_spectating(self) -> None:
        tracker = GSIStateTracker()
        _ = tracker.state_from_payload(_payload(phase="live", health=100))

        state = tracker.state_from_payload(
            _payload(
                phase="live",
                health=100,
                player_steamid="76561198000000002",
            ),
        )

        self.assertFalse(state.features_allowed)
        self.assertEqual(state.local_status, "Dead")

    def test_new_live_round_positive_health_clears_latched_death_without_ids(self) -> None:
        tracker = GSIStateTracker()
        _ = tracker.state_from_payload(_payload(phase="live", health=0, provider_steamid="", player_steamid=""))
        _ = tracker.state_from_payload(_payload(phase="over", health=0, provider_steamid="", player_steamid=""))

        state = tracker.state_from_payload(_payload(phase="live", health=100, provider_steamid="", player_steamid=""))

        self.assertTrue(state.features_allowed)
        self.assertEqual(state.local_status, "Alive")


if __name__ == "__main__":
    _ = unittest.main()
