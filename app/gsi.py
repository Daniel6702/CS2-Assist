from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable


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

    @classmethod
    def from_payload(cls, payload: dict) -> "GameState":
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
        if health is None:
            player_alive = None
        else:
            player_alive = health > 0

        round_phase = None
        for value in (
            round_info.get("phase"),
            phase_countdowns.get("phase"),
            map_info.get("phase"),
        ):
            if isinstance(value, str) and value.strip():
                round_phase = value.strip().lower()
                break

        map_name = map_info.get("name") if isinstance(map_info.get("name"), str) else None

        # Latest requested behavior:
        # automation stays disabled until GSI explicitly reports that the
        # player is alive. Unknown / missing state should not enable features.
        features_allowed = player_alive is True

        return cls(
            raw=payload,
            current_weapon=active_weapon_name,
            ammo_clip=ammo_clip,
            ammo_clip_max=ammo_clip_max,
            player_alive=player_alive,
            round_phase=round_phase,
            map_name=map_name,
            features_allowed=features_allowed,
        )


class GSIServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 3000) -> None:
        self.host = host
        self.port = port
        self._thread: threading.Thread | None = None
        self._httpd: ThreadingHTTPServer | None = None
        self._listeners: list[Callable[[GameState], None]] = []
        self.latest_state: GameState | None = None

    def add_listener(self, callback: Callable[[GameState], None]) -> None:
        self._listeners.append(callback)

    def _dispatch(self, state: GameState) -> None:
        self.latest_state = state
        for callback in list(self._listeners):
            try:
                callback(state)
            except Exception:
                pass

    def start(self) -> None:
        if self._httpd is not None:
            return

        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8"))
                    state = GameState.from_payload(payload)
                    outer._dispatch(state)
                    body = b'{"ok": true}'
                    self.send_response(200)
                except Exception as exc:
                    body = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
                    self.send_response(400)

                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args) -> None:
                return

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None
        self._httpd = None
