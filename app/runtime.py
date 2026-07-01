from __future__ import annotations

from copy import deepcopy
from typing import Callable

from app.components.base import BaseComponent
from app.components.bhop import BhopComponent
from app.components.counter_strafe import CounterStrafeComponent
from app.components.cv_trigger import CVTriggerComponent
from app.components.pixel_trigger import PixelTriggerComponent
from app.components.recoil import RecoilComponent
from app.components.snap_tap import SnapTapComponent
from app.gsi import GSIServer, GameState


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
        }
        for component in self.components.values():
            component.set_status_callback(self.status_callback)

        self.gsi_server: GSIServer | None = None
        self._gsi_enabled = False
        self._gsi_gate_open = False
        self._gsi_gate_reason = "waiting_for_alive_gsi"

    def _effective_component_config(self, profile: dict, name: str) -> dict:
        components_cfg = profile.get("components", {}) or {}
        cfg = deepcopy(dict(components_cfg.get(name, {})))
        shared = dict((profile.get("app", {}) or {}).get("shared", {}) or {})

        keyboard_device_path = str(shared.get("keyboard_device_path", "") or "")
        game_sensitivity = float(shared.get("game_sensitivity", 1.0) or 1.0)

        if name in {"bhop", "snap_tap", "counter_strafe"}:
            cfg["device_path"] = keyboard_device_path

        if name == "recoil":
            sensitivity = cfg.get("sensitivity", {})
            if not isinstance(sensitivity, dict):
                sensitivity = {}
            sensitivity["program_sens"] = game_sensitivity
            cfg["sensitivity"] = sensitivity

        if name == "cv_trigger":
            cfg["user_sens"] = game_sensitivity
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

    def configure_all(self, profile: dict) -> None:
        components_cfg = profile.get("components", {})
        for name, component in self.components.items():
            component.configure(self._effective_component_config(profile, name))
        self._apply_runtime_gate()

    def apply_enabled_states(self, profile: dict) -> None:
        components_cfg = profile.get("components", {})
        for name, component in self.components.items():
            cfg = components_cfg.get(name, {})
            should_run = bool(cfg.get("enabled", False))
            if should_run and not component.enabled:
                component.start()
            elif not should_run and component.enabled:
                component.stop()

    def restart_component(self, name: str, profile: dict) -> None:
        component = self.components[name]
        cfg = self._effective_component_config(profile, name)
        component.configure(cfg)
        component.set_runtime_gate(self._gsi_gate_open, self._gsi_gate_reason)
        if cfg.get("enabled", False):
            component.stop()
            component.start()
        else:
            component.stop()

    def stop_all(self) -> None:
        for component in self.components.values():
            component.stop()
        if self.gsi_server is not None:
            self.gsi_server.stop()
            self.gsi_server = None

    def configure_gsi(self, gsi_cfg: dict) -> None:
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
            f"[INFO] weapon={state.current_weapon} ammo={state.ammo_clip}/{state.ammo_clip_max} alive={state.player_alive} phase={state.round_phase} allowed={state.features_allowed}",
        )
        for component in self.components.values():
            try:
                component.on_gsi_state(state)
            except Exception:
                pass
