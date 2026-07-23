from __future__ import annotations

from dataclasses import dataclass


def _parse_int(value) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("-"):
            body = text[1:]
            return -int(body) if body.isdigit() else None
        return int(text) if text.isdigit() else None
    return None


def _parse_boolish(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "yes", "on"):
            return True
        if normalized in ("false", "no", "off", ""):
            return False
        parsed = _parse_int(normalized)
        return None if parsed is None else parsed != 0
    return None


@dataclass(frozen=True)
class GameState:
    raw: dict
    current_weapon: str | None
    ammo_clip: int | None
    ammo_clip_max: int | None
    player_alive: bool | None
    round_phase: str | None
    map_name: str | None
    features_allowed: bool
    kills: int | None
    team: str | None
    defusekit: bool | None
    is_scoped: bool | None
    flashed: bool | None
    local_status: str = "Not live"
    shutoff_reason: str = "round_not_live"

    @classmethod
    def from_payload(cls, payload: dict, local_status: str | None = None) -> "GameState":
        player = payload.get("player", {}) or {}
        player_state = player.get("state", {}) or {}
        weapons = player.get("weapons", {}) or {}
        round_info = payload.get("round", {}) or {}
        map_info = payload.get("map", {}) or {}
        phase_countdowns = payload.get("phase_countdowns", {}) or {}

        active_weapon_data = None
        active_weapon_name = None
        if isinstance(weapons, dict):
            for _, weapon_data in weapons.items():
                if isinstance(weapon_data, dict) and weapon_data.get("state") == "active":
                    active_weapon_data = weapon_data
                    active_weapon_name = weapon_data.get("name")
                    break
            if active_weapon_data is None:
                for _, weapon_data in weapons.items():
                    if isinstance(weapon_data, dict):
                        active_weapon_data = weapon_data
                        active_weapon_name = weapon_data.get("name")
                        break

        ammo_clip = None
        ammo_clip_max = None
        if isinstance(active_weapon_data, dict):
            ammo_clip = _parse_int(active_weapon_data.get("ammo_clip"))
            ammo_clip_max = _parse_int(active_weapon_data.get("ammo_clip_max"))

        health = _parse_int(player_state.get("health"))
        player_alive = None if health is None else health > 0

        round_phase = None
        for value in (round_info.get("phase"), phase_countdowns.get("phase"), map_info.get("phase")):
            if isinstance(value, str) and value.strip():
                round_phase = value.strip().lower()
                break

        status = local_status
        if status is None:
            if round_phase != "live":
                status = "Not live"
            elif player_alive is False:
                status = "Dead"
            else:
                status = "Alive"

        features_allowed = status == "Alive"
        shutoff_reason = _shutoff_reason(status, features_allowed)
        team = player.get("team")
        if isinstance(team, str):
            team = team.strip().upper()

        defusekit = player_state.get("defusekit")
        if isinstance(defusekit, bool):
            defusekit_bool = defusekit
        elif isinstance(defusekit, str):
            defusekit_bool = defusekit.strip().lower() in ("true", "1", "yes")
        else:
            defusekit_bool = None

        scoped_raw = player_state.get("scoped")
        if scoped_raw is None:
            scoped_raw = player_state.get("zoomed")
        if isinstance(scoped_raw, bool):
            is_scoped = scoped_raw
        elif scoped_raw in (0, 1):
            is_scoped = bool(scoped_raw)
        elif isinstance(scoped_raw, str):
            is_scoped = scoped_raw.strip().lower() in ("true", "1", "yes")
        else:
            is_scoped = None

        player_stats = player.get("match_stats", {}) or {}
        return cls(
            raw=payload,
            current_weapon=active_weapon_name,
            ammo_clip=ammo_clip,
            ammo_clip_max=ammo_clip_max,
            player_alive=player_alive,
            round_phase=round_phase,
            map_name=map_info.get("name") if isinstance(map_info.get("name"), str) else None,
            features_allowed=features_allowed,
            kills=_parse_int(player_stats.get("kills")),
            team=team,
            defusekit=defusekit_bool,
            is_scoped=is_scoped,
            flashed=_parse_boolish(player_state.get("flashed")),
            local_status=status,
            shutoff_reason=shutoff_reason,
        )


def _shutoff_reason(status: str, features_allowed: bool) -> str:
    if features_allowed:
        return ""
    if status == "Dead":
        return "player_dead"
    return "round_not_live"


class GSIStateTracker:
    def __init__(self) -> None:
        self._local_dead = False
        self._previous_round_phase: str | None = None

    def state_from_payload(self, payload: dict) -> GameState:
        return GameState.from_payload(payload, self._local_status(payload))

    def _local_status(self, payload: dict) -> str:
        provider = payload.get("provider", {}) or {}
        player = payload.get("player", {}) or {}
        player_state = player.get("state", {}) or {}
        round_data = payload.get("round", {}) or {}

        raw_round_phase = round_data.get("phase")
        round_phase = raw_round_phase.strip().lower() if isinstance(raw_round_phase, str) else None
        entering_live = round_phase == "live" and self._previous_round_phase != "live"

        if round_phase != "live":
            self._previous_round_phase = round_phase
            return "Not live"

        local_steamid = str(provider.get("steamid", ""))
        reported_steamid = str(player.get("steamid", ""))
        health = _parse_int(player_state.get("health"))
        identities_available = bool(local_steamid and reported_steamid)

        if identities_available:
            if reported_steamid != local_steamid:
                self._local_dead = True
            elif health is not None:
                self._local_dead = health <= 0
        elif health is not None:
            if health <= 0:
                self._local_dead = True
            elif entering_live:
                self._local_dead = False

        self._previous_round_phase = round_phase
        return "Dead" if self._local_dead else "Alive"
