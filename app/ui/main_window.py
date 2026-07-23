from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from PySide6 import QtCore, QtGui, QtWidgets

from app.common import deep_copy, deep_get, deep_set
from app.cs2_integration.cfg_installer import InvalidGameRootError, cfg_dir_for_game_root, validate_game_root
from app.cs2_integration.command_bridge import CS2CommandBridge
from app.cs2_integration.settings import load_settings
from app.components.pixel_trigger import PixelTriggerComponent
from app.components.recoil import RecoilComponent
from app.device_service import DeviceService
from app.profile_store import ProfileStore
from app.platform.monitor import default_monitor_geometry
from app.runtime import RuntimeManager
from app.ui.hotkeys import HotkeyBridge
from app.ui import styles
from app.ui.schemas import component_schemas
from app.ui.setup_dialog import CS2SetupDialog
from app.ui.tabs import (
    CVTriggerTab,
    LogTab,
    MiscTab,
    MovementTab,
    PixelTriggerTab,
    RecoilTab,
    SharedSettingsTab,
)
from app.ui.widgets.bomb_timer_overlay import BombTimerOverlay
from app.ui.widgets.bullet_overlay import BulletImpactOverlay
from app.ui.widgets.log_bridge import LogBridge


_COMPONENT_SCHEMA_NAMES: Final[frozenset[str]] = frozenset(name for name, _title, _schema in component_schemas())
_MOVEMENT_COMPONENTS: Final[tuple[str, ...]] = ("bhop", "snap_tap", "counter_strafe", "jump_throw", "long_jump", "auto_air_strafe")
_PIXEL_TRIGGER_SHARED_KEYS: Final[tuple[str, ...]] = (
    "game_resolution",
    "display_resolution",
    "stretched",
    "game_resolution_stretched",
)


def _deep_merge_preserving_hidden(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = deep_copy(base) if isinstance(base, dict) else {}
    for key, value in (update or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_preserving_hidden(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolution_config(value: Any, default: dict[str, int]) -> dict[str, int]:
    if not isinstance(value, dict):
        return deep_copy(default)
    return {
        "width": max(1, int(value.get("width", default["width"]) or default["width"])),
        "height": max(1, int(value.get("height", default["height"]) or default["height"])),
    }


def _pixel_trigger_config_with_shared_settings(
    pixel_trigger_cfg: dict[str, Any],
    shared_cfg: dict[str, Any],
) -> dict[str, Any]:
    cfg = deep_copy(pixel_trigger_cfg)
    cfg["game_resolution"] = _resolution_config(
        shared_cfg.get("game_resolution", cfg.get("game_resolution")),
        {"width": 1920, "height": 1080},
    )
    cfg["display_resolution"] = _resolution_config(
        shared_cfg.get("display_resolution", cfg.get("display_resolution")),
        {"width": 1920, "height": 1080},
    )
    cfg["game_resolution_stretched"] = bool(
        shared_cfg.get("game_resolution_stretched", cfg.get("stretched", True)),
    )
    return cfg


def _without_pixel_trigger_shared_keys(config: dict[str, Any]) -> dict[str, Any]:
    cleaned = deep_copy(config)
    for key in _PIXEL_TRIGGER_SHARED_KEYS:
        cleaned.pop(key, None)
    return cleaned


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, command_bridge: CS2CommandBridge | None = None) -> None:
        app = QtWidgets.QApplication.instance()
        if isinstance(app, QtWidgets.QApplication):
            styles.apply_style(app)

        super().__init__()
        self.setWindowTitle("CS2 Assist")
        self.resize(1180, 900)

        self.profile_store = ProfileStore()
        self.device_service = DeviceService()
        self.log_bridge = LogBridge()
        self.log_bridge.message.connect(self._append_log)
        self.command_bridge = command_bridge
        self.runtime = RuntimeManager(status_callback=self._runtime_status, command_bridge=command_bridge)
        self.hotkeys = HotkeyBridge(self)
        self.hotkeys.activated.connect(self._on_hotkey_activated)
        self.bullet_overlay = BulletImpactOverlay()
        self.bomb_timer_overlay = BombTimerOverlay()
        self.overlay_timer = QtCore.QTimer(self)
        self.overlay_timer.timeout.connect(self._tick_bullet_overlay)
        self.overlay_timer.timeout.connect(self._tick_bomb_timer)
        self.overlay_timer.timeout.connect(self._tick_pixel_trigger_scope_status)

        self.current_profile_name = "Default"
        self.current_profile_data = self.profile_store.load_profile(self.current_profile_name)
        self._movement_hotkey_disabled: set[str] = set()
        self._loading_profile = False
        self._closing = False
        self._overlay_active = False
        self._saved_window_flags: QtCore.Qt.WindowType = self.windowFlags()

        self.profile_combo: QtWidgets.QComboBox
        self.new_profile_btn: QtWidgets.QPushButton
        self.duplicate_profile_btn: QtWidgets.QPushButton
        self.delete_profile_btn: QtWidgets.QPushButton
        self.save_profile_btn: QtWidgets.QPushButton
        self.apply_profile_btn: QtWidgets.QPushButton
        self.refresh_devices_btn: QtWidgets.QPushButton
        self.stop_all_btn: QtWidgets.QPushButton

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.addWidget(self._build_top_bar())

        self.tabs = QtWidgets.QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_tabs()

        self._refresh_profile_list()
        self._refresh_devices()
        self.load_profile(self.current_profile_name)
        self.apply_all_runtime()
        self._configure_hotkeys()
        self.overlay_timer.start(16)

    def _build_top_bar(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        self.profile_combo = QtWidgets.QComboBox()
        self.profile_combo.currentTextChanged.connect(self._on_profile_selected)
        layout.addWidget(QtWidgets.QLabel("Profile"))
        layout.addWidget(self.profile_combo)

        self.new_profile_btn = QtWidgets.QPushButton("New")
        self.new_profile_btn.clicked.connect(self._new_profile)
        layout.addWidget(self.new_profile_btn)
        self.duplicate_profile_btn = QtWidgets.QPushButton("Duplicate")
        self.duplicate_profile_btn.clicked.connect(self._duplicate_profile)
        layout.addWidget(self.duplicate_profile_btn)
        self.delete_profile_btn = QtWidgets.QPushButton("Delete")
        self.delete_profile_btn.clicked.connect(self._delete_profile)
        layout.addWidget(self.delete_profile_btn)
        self.save_profile_btn = QtWidgets.QPushButton("Save")
        self.save_profile_btn.clicked.connect(self.save_current_profile)
        layout.addWidget(self.save_profile_btn)
        self.apply_profile_btn = QtWidgets.QPushButton("Apply")
        self.apply_profile_btn.clicked.connect(self.apply_all_runtime)
        layout.addWidget(self.apply_profile_btn)
        self.refresh_devices_btn = QtWidgets.QPushButton("Refresh Devices")
        self.refresh_devices_btn.clicked.connect(self._refresh_devices)
        layout.addWidget(self.refresh_devices_btn)
        self.stop_all_btn = QtWidgets.QPushButton("Stop All")
        self.stop_all_btn.clicked.connect(self.runtime.stop_all)
        layout.addWidget(self.stop_all_btn)
        layout.addStretch(1)
        return widget

    def _build_tabs(self) -> None:
        self.shared_settings_tab = SharedSettingsTab(self.device_service)
        self.movement_tab = MovementTab(self.device_service)
        self.recoil_tab = RecoilTab(self.device_service)
        self.pixel_trigger_tab = PixelTriggerTab(self.device_service)
        self.cv_trigger_tab = CVTriggerTab(self.device_service)
        self.misc_tab = MiscTab()
        self.log_tab = LogTab()

        self.tabs.addTab(self.shared_settings_tab, "Shared Settings")
        self.tabs.addTab(self.cv_trigger_tab, "CV Aim Assist")
        self.tabs.addTab(self.recoil_tab, "Recoil")
        self.tabs.addTab(self.pixel_trigger_tab, "Pixel Trigger")
        self.tabs.addTab(self.movement_tab, "Movement")
        self.tabs.addTab(self.misc_tab, "Misc")
        self.tabs.addTab(self.log_tab, "Log")

        # Connect signals
        self.shared_settings_tab.shared_keyboard_device.currentTextChanged.connect(self._on_shared_settings_changed)
        self.shared_settings_tab.shared_game_sensitivity.valueChanged.connect(self._on_shared_settings_changed)
        self.shared_settings_tab.shared_game_width.valueChanged.connect(self._on_shared_settings_changed)
        self.shared_settings_tab.shared_game_height.valueChanged.connect(self._on_shared_settings_changed)
        self.shared_settings_tab.shared_game_stretched.stateChanged.connect(self._on_shared_settings_changed)
        self.shared_settings_tab.shared_display_width.valueChanged.connect(self._on_shared_settings_changed)
        self.shared_settings_tab.shared_display_height.valueChanged.connect(self._on_shared_settings_changed)
        self.shared_settings_tab.gsi_host.editingFinished.connect(self._on_gsi_changed)
        self.shared_settings_tab.gsi_port.valueChanged.connect(self._on_gsi_changed)
        self.shared_settings_tab.hotkey_cv_trigger.editingFinished.connect(self._on_hotkeys_changed)
        self.shared_settings_tab.hotkey_recoil.editingFinished.connect(self._on_hotkeys_changed)
        self.shared_settings_tab.hotkey_pixel_trigger.editingFinished.connect(self._on_hotkeys_changed)
        self.shared_settings_tab.hotkey_movement.editingFinished.connect(self._on_hotkeys_changed)
        self.shared_settings_tab.hotkey_stop_all.editingFinished.connect(self._on_hotkeys_changed)
        self.shared_settings_tab.hotkey_overlay.editingFinished.connect(self._on_hotkeys_changed)
        self.shared_settings_tab.change_game_directory_requested.connect(self._change_game_directory)

        # Connect component config changed signals
        for section in self.movement_tab.sections.values():
            section.editor.config_changed.connect(self._on_component_config_changed)
        self.recoil_tab.config_changed.connect(self._on_component_config_changed)
        self.pixel_trigger_tab.config_changed.connect(self._on_component_config_changed)
        self.cv_trigger_tab.editor.config_changed.connect(self._on_component_config_changed)
        self.misc_tab.config_changed.connect(self._on_component_config_changed)

    def _bullet_overlay_settings(self) -> dict[str, Any]:
        overlay = dict(deep_get(self.current_profile_data, "components.recoil.overlay", {}) or {})
        return {
            "enabled": bool(overlay.get("enabled", False)),
            "diameter_px": max(4, int(overlay.get("diameter_px", 12) or 12)),
            "opacity": max(0.05, min(1.0, float(overlay.get("opacity", 0.9) or 0.9))),
            "screen_scale": max(0.01, float(overlay.get("screen_scale", 0.30) or 0.30)),
        }

    def _bullet_overlay_geometry(self) -> tuple[float, float, float, float] | None:
        monitor = default_monitor_geometry()
        left = float(monitor.left)
        top = float(monitor.top)
        width = float(monitor.width)
        height = float(monitor.height)
        if width <= 0 or height <= 0:
            return None
        return left, top, width, height

    def _tick_bullet_overlay(self) -> None:
        if self._closing or not hasattr(self, "current_profile_data"):
            self.bullet_overlay.hide_overlay()
            return
        settings = self._bullet_overlay_settings()
        if not settings["enabled"]:
            self.bullet_overlay.hide_overlay()
            return
        geom = self._bullet_overlay_geometry()
        if geom is None:
            self.bullet_overlay.hide_overlay()
            return
        left, top, mon_width, mon_height = geom
        self.bullet_overlay.configure(
            settings["diameter_px"],
            settings["opacity"],
            monitor_geometry=(int(left), int(top), int(mon_width), int(mon_height)),
        )
        recoil = self.runtime.components.get("recoil")
        if not isinstance(recoil, RecoilComponent):
            self.bullet_overlay.hide_overlay()
            return
        try:
            state = recoil.get_alignment_state()
        except Exception:
            self.bullet_overlay.hide_overlay()
            return
        if not isinstance(state, dict) or not bool(state.get("active", False)):
            self.bullet_overlay.hide_overlay()
            return
        try:
            mouse_x = float(state.get("mouse_offset_x", 0.0) or 0.0)
            mouse_y = float(state.get("mouse_offset_y", 0.0) or 0.0)
        except Exception:
            self.bullet_overlay.hide_overlay()
            return

        shared = dict(deep_get(self.current_profile_data, "app.shared", {}) or {})
        user_sens = max(1e-6, float(shared.get("game_sensitivity", 1.0) or 1.0))
        game_res = dict(deep_get(self.current_profile_data, "app.shared.game_resolution", {}) or {})
        if not game_res:
            game_res = dict(deep_get(self.current_profile_data, "components.cv_trigger.game_resolution", {}) or {})
        game_width = max(1.0, float(game_res.get("width", 1600) or 1600))
        game_height = max(1.0, float(game_res.get("height", 1200) or 1200))
        base_sens_mult_x = (game_width / max(1.0, mon_width)) / user_sens
        base_sens_mult_y = (game_height / max(1.0, mon_height)) / user_sens
        if abs(base_sens_mult_x) < 1e-6:
            base_sens_mult_x = 1.0
        if abs(base_sens_mult_y) < 1e-6:
            base_sens_mult_y = 1.0
        bullet_x = left + mon_width / 2.0 - (mouse_x / base_sens_mult_x) * float(settings["screen_scale"])
        bullet_y = top + mon_height / 2.0 - (mouse_y / base_sens_mult_y) * float(settings["screen_scale"])
        self.bullet_overlay.show_point(bullet_x, bullet_y)

    def _tick_bomb_timer(self) -> None:
        if self._closing:
            return

        component = self.runtime.components.get("bomb_timer")
        bomb_active = False
        remaining = 0
        team = None
        defusekit = None
        warn_enabled = True
        font_size = 48
        color_str = "#FF3232"

        if component is not None and component.enabled:
            state = component.get_state()
            bomb_active = bool(state.get("bomb_planted", False))
            remaining = int(state.get("remaining", 0))
            team = state.get("team")
            defusekit = state.get("defusekit")
            cfg = component.config
            warn_enabled = bool(cfg.get("defuse_warning_enabled", True))
            font_size = int(cfg.get("overlay_font_size", 48))
            color_str = str(cfg.get("overlay_color", "#FF3232"))

        show_warning = False
        if warn_enabled and bomb_active and team == "CT":
            defuse_limit = 5 if defusekit else 10
            show_warning = remaining < defuse_limit

        self.bomb_timer_overlay.update_state(
            bomb_active, remaining, show_warning, font_size, color_str,
        )

    def _runtime_status(self, source: str, message: str) -> None:
        if self._closing or not hasattr(self, "current_profile_data"):
            return
        try:
            self.log_bridge.message.emit(source, message)
        except RuntimeError:
            return

    def _append_log(self, source: str, message: str) -> None:
        self.log_tab.append_log(source, message)
        movement_section = self.movement_tab.get_section(source)
        if movement_section is not None:
            movement_section.set_runtime_status(message.replace("[INFO] ", "").replace("[WARNING] ", "").replace("[ERROR] ", ""))
        elif source == "recoil":
            self.recoil_tab.set_runtime_status(message.replace("[INFO] ", "").replace("[WARNING] ", "").replace("[ERROR] ", ""))
        elif source == "pixel_trigger":
            self.pixel_trigger_tab.set_runtime_status(message.replace("[INFO] ", "").replace("[WARNING] ", "").replace("[ERROR] ", ""))
        elif source == "cv_trigger":
            self.cv_trigger_tab.set_runtime_status(message.replace("[INFO] ", "").replace("[WARNING] ", "").replace("[ERROR] ", ""))
        elif source == "gsi_connection":
            self.shared_settings_tab.set_gsi_connection_status(message == "Connected")
        elif source == "gsi_shutoff":
            self.shared_settings_tab.set_gsi_system_active(message == "Active")
        elif source == "gsi" and "weapon=" in message:
            clean = message.replace("[INFO] ", "")
            self.shared_settings_tab.set_last_state(clean)

    def _tick_pixel_trigger_scope_status(self) -> None:
        if self._closing:
            return
        component = self.runtime.components.get("pixel_trigger")
        if isinstance(component, PixelTriggerComponent):
            self.pixel_trigger_tab.set_scoped_status(component.scope_state())

    def _refresh_profile_list(self) -> None:
        names = self.profile_store.list_profile_names()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems(names)
        index = self.profile_combo.findText(self.current_profile_name)
        if index >= 0:
            self.profile_combo.setCurrentIndex(index)
        self.profile_combo.blockSignals(False)

    def _refresh_devices(self) -> None:
        self.shared_settings_tab.refresh_devices()
        self.movement_tab.refresh_devices()
        self.recoil_tab.refresh_devices()
        self.pixel_trigger_tab.refresh_devices()
        self.cv_trigger_tab.refresh_devices()

    def load_profile(self, name: str) -> None:
        self._loading_profile = True
        try:
            self.current_profile_name = name
            self.current_profile_data = self.profile_store.load_profile(name)
            app_config = deep_copy(deep_get(self.current_profile_data, "app", {}) or {})
            if not deep_get(app_config, "shared.game_resolution"):
                legacy_game_resolution = deep_get(self.current_profile_data, "components.cv_trigger.game_resolution")
                if isinstance(legacy_game_resolution, dict):
                    deep_set(app_config, "shared.game_resolution", legacy_game_resolution)
            if not deep_get(app_config, "shared.display_resolution"):
                legacy_display_resolution = deep_get(self.current_profile_data, "components.pixel_trigger.display_resolution")
                if isinstance(legacy_display_resolution, dict):
                    deep_set(app_config, "shared.display_resolution", legacy_display_resolution)
            if deep_get(app_config, "shared.game_resolution_stretched") is None:
                legacy_stretched = deep_get(self.current_profile_data, "components.pixel_trigger.stretched", True)
                deep_set(app_config, "shared.game_resolution_stretched", bool(legacy_stretched))
            app_config.pop("safety", None)
            deep_set(self.current_profile_data, "app", app_config)
            self.shared_settings_tab.load_config(app_config)
            self.movement_tab.load_config(deep_get(self.current_profile_data, "components", {}))
            self.recoil_tab.load_config(deep_get(self.current_profile_data, "components.recoil", {}))
            self._load_pixel_trigger_from_profile()

            self.cv_trigger_tab.load_config(deep_get(self.current_profile_data, "components.cv_trigger", {}))
            self.misc_tab.load_config("kill_sound", deep_get(self.current_profile_data, "components.kill_sound", {}))
            self.misc_tab.load_config("bomb_timer", deep_get(self.current_profile_data, "components.bomb_timer", {}))
            self.misc_tab.load_config("auto_shoot", deep_get(self.current_profile_data, "components.auto_shoot", {}))
            self.misc_tab.load_config("flash_filter", deep_get(self.current_profile_data, "components.flash_filter", {}))
            self._movement_hotkey_disabled.clear()
            self._configure_hotkeys()
        finally:
            self._loading_profile = False

    def _load_pixel_trigger_from_profile(self) -> None:
        pixel_trigger_cfg = deep_get(self.current_profile_data, "components.pixel_trigger", {}) or {}
        shared_cfg = deep_get(self.current_profile_data, "app.shared", {}) or {}
        self.pixel_trigger_tab.load_config(
            _pixel_trigger_config_with_shared_settings(
                pixel_trigger_cfg if isinstance(pixel_trigger_cfg, dict) else {},
                shared_cfg if isinstance(shared_cfg, dict) else {},
            ),
        )

    def save_current_profile(self) -> None:
        self.profile_store.save_profile(self.current_profile_name, self.current_profile_data)
        self._append_log("app", f"Saved profile '{self.current_profile_name}'.")

    def _create_command_bridge_from_settings(self) -> CS2CommandBridge | None:
        settings = load_settings()
        if not settings.cs2_game_root:
            return None
        root = Path(settings.cs2_game_root)
        try:
            validate_game_root(root)
        except InvalidGameRootError:
            return None
        return CS2CommandBridge(cfg_dir_for_game_root(root))

    def _change_game_directory(self) -> None:
        dialog = CS2SetupDialog(parent=self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        new_bridge = self._create_command_bridge_from_settings()
        if new_bridge is None:
            self._append_log("app", "[ERROR] CS2 game directory was saved, but the command bridge could not be created.")
            return
        long_jump_was_enabled = bool(deep_get(self.current_profile_data, "components.long_jump.enabled", False))
        if long_jump_was_enabled:
            self.runtime.components["long_jump"].stop()
        old_bridge = self.command_bridge
        self.command_bridge = new_bridge
        self.runtime.set_command_bridge(new_bridge)
        if old_bridge is not None:
            old_bridge.close()
        if long_jump_was_enabled:
            self.runtime.restart_component("long_jump", self.current_profile_data)
        self._append_log("app", "[INFO] CS2 game directory updated.")

    def apply_all_runtime(self) -> None:
        self._sync_current_profile_from_widgets()
        self.save_current_profile()
        self.runtime.configure_all(self.current_profile_data)
        self.runtime.configure_gsi(deep_get(self.current_profile_data, "app.gsi", {}))
        self.runtime.apply_enabled_states(self.current_profile_data)
        self._configure_hotkeys()
        self._append_log("app", f"Applied profile '{self.current_profile_name}'.")

    def _sync_current_profile_from_widgets(self) -> None:
        shared_config = self.shared_settings_tab.extract_config()
        for key, value in shared_config.get("gsi", {}).items():
            deep_set(self.current_profile_data, f"app.gsi.{key}", value)
        for key, value in shared_config.get("shared", {}).items():
            deep_set(self.current_profile_data, f"app.shared.{key}", value)
        for key, value in shared_config.get("hotkeys", {}).items():
            deep_set(self.current_profile_data, f"app.hotkeys.{key}", value)

        movement_config = self.movement_tab.extract_config()
        for name, config in movement_config.items():
            deep_set(self.current_profile_data, f"components.{name}", config)

        for name, editor in [
            ("recoil", self.recoil_tab),
            ("pixel_trigger", self.pixel_trigger_tab),
            ("cv_trigger", self.cv_trigger_tab),
        ]:
            extracted = editor.extract_config()
            if name == "cv_trigger":
                cfg = deep_copy(extracted if isinstance(extracted, dict) else {})
            else:
                existing = deep_get(self.current_profile_data, f"components.{name}", {})
                cfg = _deep_merge_preserving_hidden(existing if isinstance(existing, dict) else {}, extracted)
            if name == "pixel_trigger":
                cfg = _without_pixel_trigger_shared_keys(cfg)
            deep_set(self.current_profile_data, f"components.{name}", cfg)

        # Misc tab returns {kill_sound: …, bomb_timer: …}
        misc_cfgs = self.misc_tab.extract_config()
        for section_name, section_cfg in misc_cfgs.items():
            existing = deep_get(self.current_profile_data, f"components.{section_name}", {})
            merged = _deep_merge_preserving_hidden(existing if isinstance(existing, dict) else {}, section_cfg)
            deep_set(self.current_profile_data, f"components.{section_name}", merged)

    def _on_component_config_changed(self, component_name: str, config: dict[str, Any]) -> None:
        if self._loading_profile:
            return
        
        existing = deep_get(self.current_profile_data, f"components.{component_name}", {})
        if component_name == "cv_trigger":
            merged = deep_copy(config if isinstance(config, dict) else {})
        else:
            merged = _deep_merge_preserving_hidden(existing if isinstance(existing, dict) else {}, config)
        if component_name == "pixel_trigger":
            merged = _without_pixel_trigger_shared_keys(merged)
        deep_set(self.current_profile_data, f"components.{component_name}", merged)
        self.profile_store.save_profile(self.current_profile_name, self.current_profile_data)
        if component_name == "cv_trigger":
            self.cv_trigger_tab.mark_runtime_waiting()
        self.runtime.restart_component(component_name, self.current_profile_data)

    def _on_shared_settings_changed(self) -> None:
        if self._loading_profile:
            return
        self._sync_current_profile_from_widgets()
        self._loading_profile = True
        try:
            self._load_pixel_trigger_from_profile()
        finally:
            self._loading_profile = False
        self.profile_store.save_profile(self.current_profile_name, self.current_profile_data)
        for name in ("bhop", "snap_tap", "counter_strafe", "long_jump", "auto_air_strafe", "recoil", "pixel_trigger", "cv_trigger"):
            self.runtime.restart_component(name, self.current_profile_data)

    def _on_hotkeys_changed(self) -> None:
        if self._loading_profile:
            return
        self._sync_current_profile_from_widgets()
        self.profile_store.save_profile(self.current_profile_name, self.current_profile_data)
        self._configure_hotkeys()

    def _configure_hotkeys(self) -> None:
        if self._closing or not hasattr(self, "current_profile_data"):
            return
        hotkeys = dict(deep_get(self.current_profile_data, "app.hotkeys", {}) or {})
        try:
            self.hotkeys.configure({key: str(value) for key, value in hotkeys.items()})
            mode = self.hotkeys.mode
            if mode == "fallback":
                self._append_log("hotkeys", "[WARN] Using fallback hotkey listener (GlobalHotKeys unavailable). Hotkeys active.")
            elif mode == "none":
                self._append_log("hotkeys", "[INFO] No hotkeys configured.")
        except Exception as exc:
            self._append_log("hotkeys", f"[ERROR] Failed to configure hotkeys: {exc}")

    def _on_hotkey_activated(self, action: str) -> None:
        if self._closing:
            return
        if action == "cv_trigger":
            self._toggle_component_enabled("cv_trigger")
        elif action == "recoil":
            self._toggle_component_enabled("recoil")
        elif action == "pixel_trigger":
            self._toggle_component_enabled("pixel_trigger")
        elif action == "movement":
            self._toggle_movement_enabled()
        elif action == "stop_all":
            self.runtime.stop_all()
            self._append_log("hotkeys", "[INFO] Stop All triggered by hotkey.")
        elif action == "overlay":
            self._toggle_overlay()

    def _toggle_overlay(self) -> None:
        if self._overlay_active:
            self.setWindowFlags(self._saved_window_flags)
            self._overlay_active = False
            self._append_log("hotkeys", "[INFO] Overlay disabled.")
        else:
            self._saved_window_flags = self.windowFlags()
            # X11BypassWindowManagerHint is required for the window to appear
            # above a fullscreen game — without it the compositor keeps the
            # game on top.  The BulletImpactOverlay uses the same flag.
            self.setWindowFlags(
                self._saved_window_flags
                | QtCore.Qt.WindowType.WindowStaysOnTopHint
                | QtCore.Qt.WindowType.X11BypassWindowManagerHint
            )
            self._overlay_active = True
            self._append_log("hotkeys", "[INFO] Overlay enabled (always-on-top).")
        saved = self.geometry()
        self.show()
        self.setGeometry(saved)
        if self._overlay_active:
            self.raise_()
            self.activateWindow()

    def _toggle_component_enabled(self, name: str) -> None:
        self._sync_current_profile_from_widgets()
        current = bool(deep_get(self.current_profile_data, f"components.{name}.enabled", False))
        self._set_component_enabled(name, not current)
        state = "enabled" if not current else "disabled"
        self._append_log("hotkeys", f"[INFO] {name} {state} by hotkey.")

    def _toggle_movement_enabled(self) -> None:
        self._sync_current_profile_from_widgets()
        enabled = {
            name
            for name in _MOVEMENT_COMPONENTS
            if bool(deep_get(self.current_profile_data, f"components.{name}.enabled", False))
        }
        if enabled:
            self._movement_hotkey_disabled = set(enabled)
            for name in enabled:
                self._set_component_enabled(name, False, save=False)
            self.profile_store.save_profile(self.current_profile_name, self.current_profile_data)
            self._append_log("hotkeys", "[INFO] Movement disabled by hotkey.")
            return

        if not self._movement_hotkey_disabled:
            self._append_log("hotkeys", "[INFO] No movement components to restore from hotkey.")
            return

        restored = sorted(self._movement_hotkey_disabled)
        for name in restored:
            self._set_component_enabled(name, True, save=False)
        self._movement_hotkey_disabled.clear()
        self.profile_store.save_profile(self.current_profile_name, self.current_profile_data)
        self._append_log("hotkeys", "[INFO] Movement restored by hotkey.")

    def _set_component_enabled(self, name: str, enabled: bool, save: bool = True) -> None:
        deep_set(self.current_profile_data, f"components.{name}.enabled", enabled)
        if name in _MOVEMENT_COMPONENTS:
            section = self.movement_tab.get_section(name)
            if section is not None:
                section.load_config(deep_get(self.current_profile_data, f"components.{name}", {}))
        elif name == "recoil":
            self.recoil_tab.load_config(deep_get(self.current_profile_data, "components.recoil", {}))
        elif name == "pixel_trigger":
            self._load_pixel_trigger_from_profile()
        elif name == "cv_trigger":
            self.cv_trigger_tab.load_config(deep_get(self.current_profile_data, "components.cv_trigger", {}))
        elif name == "bomb_timer":
            self.misc_tab.load_config("bomb_timer", deep_get(self.current_profile_data, "components.bomb_timer", {}))
        elif name == "kill_sound":
            self.misc_tab.load_config("kill_sound", deep_get(self.current_profile_data, "components.kill_sound", {}))
        elif name == "auto_shoot":
            self.misc_tab.load_config("auto_shoot", deep_get(self.current_profile_data, "components.auto_shoot", {}))
        elif name == "flash_filter":
            self.misc_tab.load_config("flash_filter", deep_get(self.current_profile_data, "components.flash_filter", {}))
        self.runtime.restart_component(name, self.current_profile_data)
        if save:
            self.profile_store.save_profile(self.current_profile_name, self.current_profile_data)

    def _on_gsi_changed(self) -> None:
        if self._loading_profile:
            return
        self._sync_current_profile_from_widgets()
        self.profile_store.save_profile(self.current_profile_name, self.current_profile_data)
        self.runtime.configure_gsi(deep_get(self.current_profile_data, "app.gsi", {}))

    def _on_profile_selected(self, name: str) -> None:
        if not name:
            return
        self.load_profile(name)
        self.apply_all_runtime()

    def _new_profile(self) -> None:
        name, ok = QtWidgets.QInputDialog.getText(self, "New Profile", "Profile name")
        if not ok or not name.strip():
            return
        self.current_profile_name = name.strip()
        self.current_profile_data = self.profile_store.create_profile(self.current_profile_name)
        self._refresh_profile_list()
        self.load_profile(self.current_profile_name)

    def _duplicate_profile(self) -> None:
        name, ok = QtWidgets.QInputDialog.getText(self, "Duplicate Profile", "New profile name")
        if not ok or not name.strip():
            return
        payload = deep_copy(self.current_profile_data)
        self.current_profile_name = name.strip()
        self.current_profile_data = self.profile_store.create_profile(self.current_profile_name, payload)
        self._refresh_profile_list()
        self.load_profile(self.current_profile_name)

    def _delete_profile(self) -> None:
        if self.current_profile_name.lower() == "default":
            QtWidgets.QMessageBox.warning(self, "Delete Profile", "Default profile cannot be deleted.")
            return
        confirm = QtWidgets.QMessageBox.question(self, "Delete Profile", f"Delete profile '{self.current_profile_name}'?")
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.profile_store.delete_profile(self.current_profile_name)
        self.current_profile_name = "Default"
        self._refresh_profile_list()
        self.load_profile(self.current_profile_name)
        self.apply_all_runtime()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._closing = True
        self.hotkeys.stop()
        self.bullet_overlay.hide_overlay()
        for component in self.runtime.components.values():
            component.set_status_callback(lambda *_args, **_kwargs: None)
        self.runtime.stop_all()
        if self.command_bridge is not None:
            self.command_bridge.close()
        super().closeEvent(event)
