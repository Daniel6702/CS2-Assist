from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from app.components.base import BaseComponent
from app.components.bhop import BhopComponent
from app.components.counter_strafe import CounterStrafeComponent
from app.components import AutoAcceptComponent, AutoAirStrafeComponent, AutoShootComponent, BombTimerComponent, CVTriggerComponent, FlashFilterComponent, JumpThrowComponent, KillSoundComponent, LongJumpComponent
from app.components.long_jump import CommandBridge
from app.components.pixel_trigger import PixelTriggerComponent
from app.components.recoil import RecoilComponent
from app.components.snap_tap import SnapTapComponent
from app.gsi import GSIServer, GameState
from app.platform.monitor import default_monitor_geometry


_SYSTEM_MODES = frozenset({"on", "off", "gsi"})


class RuntimeManager:
    def __init__(
        self,
        status_callback: Callable[[str, str], None],
        command_bridge: CommandBridge | None = None,
        cs2_log_path_provider: Callable[[], Path | None] | None = None,
    ) -> None:
        self.status_callback = status_callback
        self._cs2_log_path_provider = cs2_log_path_provider
        self.components: dict[str, BaseComponent] = {
            "bhop": BhopComponent(),
            "snap_tap": SnapTapComponent(),
            "counter_strafe": CounterStrafeComponent(),
            "jump_throw": JumpThrowComponent(),
            "long_jump": LongJumpComponent(command_bridge=command_bridge),
            "auto_air_strafe": AutoAirStrafeComponent(),
            "recoil": RecoilComponent(),
            "pixel_trigger": PixelTriggerComponent(),
            "cv_trigger": CVTriggerComponent(),
            "kill_sound": KillSoundComponent(),
            "bomb_timer": BombTimerComponent(),
            "auto_accept": AutoAcceptComponent(),
            "auto_shoot": AutoShootComponent(),
            "flash_filter": FlashFilterComponent(),
        }
        for component in self.components.values():
            component.set_status_callback(self.status_callback)

        self.gsi_server: GSIServer | None = None
        self._gsi_gate_open = False
        self._gsi_gate_reason = "waiting_for_gsi"
        self._gsi_connected = False
        self._system_mode = "gsi"

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

        if name in {"bhop", "snap_tap", "counter_strafe", "jump_throw", "long_jump", "auto_air_strafe"}:
            cfg["device_path"] = keyboard_device_path

        if name == "auto_air_strafe":
            cfg["game_sensitivity"] = game_sensitivity

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

        if name == "auto_accept" and self._cs2_log_path_provider is not None:
            path = self._cs2_log_path_provider()
            if path is not None:
                cfg["console_log_path"] = str(path)

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

    def _set_gsi_connection_status(self, connected: bool, *, force: bool = False) -> None:
        if not force and self._gsi_connected == connected:
            return
        self._gsi_connected = connected
        message = "Connected" if connected else "Waiting for connection ..."
        self.status_callback("gsi_connection", message)

    def _set_runtime_gate(self, open_: bool, reason: str) -> None:
        changed = self._gsi_gate_open != open_ or self._gsi_gate_reason != reason
        self._gsi_gate_open = open_
        self._gsi_gate_reason = reason
        self._apply_runtime_gate()
        if changed:
            self.status_callback("gsi_shutoff", "Active" if open_ else "Inactive")

    def _set_system_mode_gate(self) -> None:
        if self._system_mode == "on":
            self._set_runtime_gate(True, "")
            return
        if self._system_mode == "off":
            self._set_runtime_gate(False, "manual_off")
            return
        self._set_runtime_gate(False, "waiting_for_gsi")

    def set_command_bridge(self, command_bridge: CommandBridge | None) -> None:
        component = self.components["long_jump"]
        if isinstance(component, LongJumpComponent):
            component.set_command_bridge(command_bridge)

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
        host = str(gsi_cfg.get("host", "127.0.0.1"))
        port = int(gsi_cfg.get("port", 3000))
        mode = str(gsi_cfg.get("mode", "gsi")).strip().lower()
        self._system_mode = mode if mode in _SYSTEM_MODES else "gsi"

        if self.gsi_server is not None:
            self.gsi_server.stop()
            self.gsi_server = None

        self._set_gsi_connection_status(False, force=True)
        self._set_system_mode_gate()
        self.status_callback("gsi_shutoff", "Active" if self._gsi_gate_open else "Inactive")

        try:
            self.gsi_server = GSIServer(host=host, port=port)
            self.gsi_server.add_listener(self.on_gsi_state)
            self.gsi_server.add_connection_listener(lambda: self._set_gsi_connection_status(True))
            self.gsi_server.start()
            self.status_callback(
                "gsi",
                f"[INFO] GSI listening on http://{host}:{port}. Systems stay shut off until GSI reports live play with the local player alive.",
            )
        except Exception as exc:
            self.gsi_server = None
            if self._system_mode != "on":
                self._set_runtime_gate(False, "gsi_unavailable")
            self.status_callback("gsi", f"[ERROR] Failed to start GSI server: {exc}")

    def on_gsi_state(self, state: GameState) -> None:
        allowed = bool(state.features_allowed)
        reason = "" if allowed else state.shutoff_reason or "gsi_shutoff"
        if self._system_mode == "gsi":
            self._set_runtime_gate(allowed, reason)

        self.status_callback(
            "gsi",
            f"[INFO] weapon={state.current_weapon} ammo={state.ammo_clip}/{state.ammo_clip_max} local={state.local_status} phase={state.round_phase} allowed={state.features_allowed} scoped={state.is_scoped}",
        )
        for component in self.components.values():
            try:
                component.on_gsi_state(state)
            except Exception:
                pass
