from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from app.components.base import BaseComponent
from app.components.bhop import BhopComponent
from app.components.counter_strafe import CounterStrafeComponent
from app.components import AutoShootComponent, BombTimerComponent, CVTriggerComponent, KillSoundComponent
from app.components.pixel_trigger import PixelTriggerComponent
from app.components.recoil import RecoilComponent
from app.components.snap_tap import SnapTapComponent
from app.gsi import GSIServer, GameState
from app.platform.monitor import default_monitor_geometry


class RuntimeManager:
    def __init__(self, status_callback: Callable[[str, str], None]) -> None:
        self.status_callback = status_callback
        self.components: dict[str, BaseComponent] = {
            "bhop": BhopComponent(),
            "snap_tap": SnapTapComponent(),
            "counter_strafe": CounterStrafeComponent(),
            "recoil": RecoilComponent(),
            "pixel_trigger": PixelTriggerComponent(),
            "cv_trigger": CVTriggerComponent(),
            "kill_sound": KillSoundComponent(),
            "bomb_timer": BombTimerComponent(),
            "auto_shoot": AutoShootComponent(),
        }
        for component in self.components.values():
            component.set_status_callback(self.status_callback)

        self.gsi_server: GSIServer | None = None
        self._gsi_enabled = False
        self._gsi_gate_open = False
        self._gsi_gate_reason = "waiting_for_alive_gsi"

    def _effective_component_config(self, profile: dict[str, Any], name: str) -> dict[str, Any]:
        components_cfg = profile.get("components", {}) or {}
        cfg = deepcopy(dict(components_cfg.get(name, {})))
        shared = dict((profile.get("app", {}) or {}).get("shared", {}) or {})

        keyboard_device_path = str(shared.get("keyboard_device_path", "") or "")
        game_sensitivity = float(shared.get("game_sensitivity", 1.0) or 1.0)
        game_resolution = shared.get("game_resolution")
        if not isinstance(game_resolution, dict):
            game_resolution = cfg.get("game_resolution", {"width": 1600, "height": 1200})
        if not isinstance(game_resolution, dict):
            game_resolution = {"width": 1600, "height": 1200}
        display_resolution = shared.get("display_resolution")
        if not isinstance(display_resolution, dict):
            display_resolution = cfg.get("display_resolution", {"width": 1920, "height": 1080})
        if not isinstance(display_resolution, dict):
            display_resolution = {"width": 1920, "height": 1080}

        if name in {"bhop", "snap_tap", "counter_strafe"}:
            cfg["device_path"] = keyboard_device_path

        if name == "recoil":
            sensitivity = cfg.get("sensitivity", {})
            if not isinstance(sensitivity, dict):
                sensitivity = {}
            sensitivity["program_sens"] = game_sensitivity
            cfg["sensitivity"] = sensitivity

        if name in {"cv_trigger", "bomb_timer"}:
            cfg["game_resolution"] = {
                "width": max(1, int(game_resolution.get("width", 1600) or 1600)),
                "height": max(1, int(game_resolution.get("height", 1200) or 1200)),
            }

        if name == "pixel_trigger":
            cfg["game_resolution"] = {
                "width": max(1, int(game_resolution.get("width", 1600) or 1600)),
                "height": max(1, int(game_resolution.get("height", 1200) or 1200)),
            }
            cfg["display_resolution"] = {
                "width": max(1, int(display_resolution.get("width", 1920) or 1920)),
                "height": max(1, int(display_resolution.get("height", 1080) or 1080)),
            }
            cfg["game_resolution_stretched"] = bool(
                shared.get("game_resolution_stretched", cfg.get("stretched", True)),
            )

        if name == "cv_trigger":
            cfg["user_sens"] = game_sensitivity
            cfg["monitor"] = default_monitor_geometry().as_capture_dict()
            recoil_cfg = deepcopy(dict(components_cfg.get("recoil", {})))
            recoil_sens = recoil_cfg.get("sensitivity", {})
            if not isinstance(recoil_sens, dict):
                recoil_sens = {}
            recoil_sens["program_sens"] = game_sensitivity
            recoil_cfg["sensitivity"] = recoil_sens
            overlay_cfg = recoil_cfg.get("overlay", {})
            if not isinstance(overlay_cfg, dict):
                overlay_cfg = {}
            recoil_cfg["overlay"] = overlay_cfg
            recoil_cfg["screen_space_scale"] = float(
                recoil_cfg.get("screen_space_scale", overlay_cfg.get("screen_scale", 0.30)) or 0.30
            )
            cfg["recoil_sync"] = recoil_cfg
            recoil_component = self.components.get("recoil")
            provider = getattr(recoil_component, "get_alignment_state", None)
            if callable(provider):
                cfg["recoil_runtime_provider"] = provider

        return cfg

    def _apply_runtime_gate(self) -> None:
        for component in self.components.values():
            component.set_runtime_gate(self._gsi_gate_open, self._gsi_gate_reason)

    def configure_all(self, profile: dict[str, Any]) -> None:
        components_cfg = profile.get("components", {})
        for name, component in self.components.items():
            component.configure(self._effective_component_config(profile, name))
        self._apply_runtime_gate()

    def apply_enabled_states(self, profile: dict[str, Any]) -> None:
        components_cfg = profile.get("components", {})
        for name, component in self.components.items():
            cfg = components_cfg.get(name, {})
            should_run = bool(cfg.get("enabled", False))
            if should_run and not component.enabled:
                component.start()
            elif not should_run and component.enabled:
                component.stop()

    def restart_component(self, name: str, profile: dict[str, Any]) -> None:
        component = self.components[name]
        cfg = self._effective_component_config(profile, name)
        now_enabled = bool(cfg.get("enabled", False))

        if name == "cv_trigger" and component.enabled and now_enabled:
            component.stop()
            component.configure(cfg)
            component.set_runtime_gate(self._gsi_gate_open, self._gsi_gate_reason)
            component.start()
            return

        component.configure(cfg)
        component.set_runtime_gate(self._gsi_gate_open, self._gsi_gate_reason)

        if component.enabled and now_enabled:
            # Already running and should stay running — just push config.
            # The thread picks it up from self._config on its next iteration
            # (or on a manual stop/start for snapshot-based components).
            return
        if now_enabled:
            component.start()
        else:
            component.stop()

    def stop_all(self) -> None:
        for component in self.components.values():
            component.stop()
        if self.gsi_server is not None:
            self.gsi_server.stop()
            self.gsi_server = None

    def configure_gsi(self, gsi_cfg: dict[str, Any]) -> None:
        enabled = bool(gsi_cfg.get("enabled", True))
        host = str(gsi_cfg.get("host", "127.0.0.1"))
        port = int(gsi_cfg.get("port", 3000))

        if self.gsi_server is not None:
            self.gsi_server.stop()
            self.gsi_server = None

        self._gsi_enabled = enabled
        if not enabled:
            self._gsi_gate_open = True
            self._gsi_gate_reason = ""
            self._apply_runtime_gate()
            self.status_callback("gsi", "[INFO] GSI disabled. Runtime gate is open.")
            return

        # When GSI is enabled, features must remain disabled until GSI has
        # explicitly confirmed that the player is alive.
        self._gsi_gate_open = False
        self._gsi_gate_reason = "waiting_for_alive_gsi"
        self._apply_runtime_gate()

        try:
            self.gsi_server = GSIServer(host=host, port=port)
            self.gsi_server.add_listener(self.on_gsi_state)
            self.gsi_server.start()
            self.status_callback(
                "gsi",
                f"[INFO] GSI listening on http://{host}:{port}. Features stay disabled until GSI confirms the player is alive.",
            )
        except Exception as exc:
            self.gsi_server = None
            self._gsi_gate_open = False
            self._gsi_gate_reason = "waiting_for_alive_gsi"
            self._apply_runtime_gate()
            self.status_callback("gsi", f"[ERROR] Failed to start GSI server: {exc}")

    def on_gsi_state(self, state: GameState) -> None:
        allowed = bool(state.features_allowed)
        reason = "" if allowed else "player_dead"
        if self._gsi_enabled and (allowed != self._gsi_gate_open or reason != self._gsi_gate_reason):
            self._gsi_gate_open = allowed
            self._gsi_gate_reason = reason
            self._apply_runtime_gate()
            gate_text = "OPEN" if allowed else "CLOSED"
            self.status_callback("gsi", f"[INFO] Runtime gate {gate_text}.")

        self.status_callback(
            "gsi",
            f"[INFO] weapon={state.current_weapon} ammo={state.ammo_clip}/{state.ammo_clip_max} alive={state.player_alive} phase={state.round_phase} allowed={state.features_allowed} scoped={state.is_scoped}",
        )
        for component in self.components.values():
            try:
                component.on_gsi_state(state)
            except Exception:
                pass
