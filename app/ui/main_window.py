from __future__ import annotations

from typing import Any, Final

from PySide6 import QtCore, QtGui, QtWidgets

from app.common import deep_copy, deep_get, deep_set
from app.device_service import DeviceService
from app.profile_store import ProfileStore
from app.runtime import RuntimeManager
from app.ui import styles
from app.ui.schemas import component_schemas
from app.ui.tabs import (
    CVTriggerTab,
    LogTab,
    MovementTab,
    PixelTriggerTab,
    RecoilTab,
    SharedSettingsTab,
)
from app.ui.widgets import BulletImpactOverlay, LogBridge


_COMPONENT_SCHEMA_NAMES: Final[frozenset[str]] = frozenset(name for name, _title, _schema in component_schemas())


def _deep_merge_preserving_hidden(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = deep_copy(base) if isinstance(base, dict) else {}
    for key, value in (update or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_preserving_hidden(merged[key], value)
        else:
            merged[key] = value
    return merged


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
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
        self.runtime = RuntimeManager(status_callback=self._runtime_status)
        self.bullet_overlay = BulletImpactOverlay()
        self.overlay_timer = QtCore.QTimer(self)
        self.overlay_timer.timeout.connect(self._tick_bullet_overlay)

        self.current_profile_name = "Default"
        self.current_profile_data = self.profile_store.load_profile(self.current_profile_name)
        self._loading_profile = False
        self._closing = False

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
        self.log_tab = LogTab()

        self.tabs.addTab(self.shared_settings_tab, "Shared Settings")
        self.tabs.addTab(self.movement_tab, "Movement")
        self.tabs.addTab(self.recoil_tab, "Recoil")
        self.tabs.addTab(self.pixel_trigger_tab, "Pixel Trigger")
        self.tabs.addTab(self.cv_trigger_tab, "CV Trigger")
        self.tabs.addTab(self.log_tab, "Log")

        # Connect signals
        self.shared_settings_tab.shared_keyboard_device.currentTextChanged.connect(self._on_shared_settings_changed)
        self.shared_settings_tab.shared_game_sensitivity.valueChanged.connect(self._on_shared_settings_changed)
        self.shared_settings_tab.gsi_enabled.stateChanged.connect(self._on_gsi_changed)
        self.shared_settings_tab.gsi_host.editingFinished.connect(self._on_gsi_changed)
        self.shared_settings_tab.gsi_port.valueChanged.connect(self._on_gsi_changed)

        # Connect component config changed signals
        for section in self.movement_tab.sections.values():
            section.editor.config_changed.connect(self._on_component_config_changed)
        self.recoil_tab.editor.config_changed.connect(self._on_component_config_changed)
        self.pixel_trigger_tab.editor.config_changed.connect(self._on_component_config_changed)
        self.cv_trigger_tab.editor.config_changed.connect(self._on_component_config_changed)

    def _bullet_overlay_settings(self) -> dict[str, Any]:
        overlay = dict(deep_get(self.current_profile_data, "components.recoil.overlay", {}) or {})
        return {
            "enabled": bool(overlay.get("enabled", False)),
            "diameter_px": max(4, int(overlay.get("diameter_px", 12) or 12)),
            "opacity": max(0.05, min(1.0, float(overlay.get("opacity", 0.9) or 0.9))),
            "screen_scale": max(0.01, float(overlay.get("screen_scale", 0.30) or 0.30)),
        }

    def _bullet_overlay_geometry(self) -> tuple[float, float, float, float] | None:
        monitor = dict(deep_get(self.current_profile_data, "components.cv_trigger.monitor", {}) or {})
        if not monitor:
            screen = QtGui.QGuiApplication.primaryScreen()
            if screen is None:
                return None
            geom = screen.geometry()
            return float(geom.x()), float(geom.y()), float(geom.width()), float(geom.height())
        try:
            left = float(monitor.get("left", 0))
            top = float(monitor.get("top", 0))
            width = float(monitor.get("width", 0))
            height = float(monitor.get("height", 0))
        except Exception:
            return None
        if width <= 0 or height <= 0:
            return None
        return left, top, width, height

    def _tick_bullet_overlay(self) -> None:
        if self._closing or not hasattr(self, "current_profile_data"):
            self.bullet_overlay.hide_overlay()
            return
        settings = self._bullet_overlay_settings()
        self.bullet_overlay.configure(settings["diameter_px"], settings["opacity"])
        if not settings["enabled"]:
            self.bullet_overlay.hide_overlay()
            return
        recoil = self.runtime.components.get("recoil")
        if recoil is None or not hasattr(recoil, "get_alignment_state"):
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
        geom = self._bullet_overlay_geometry()
        if geom is None:
            self.bullet_overlay.hide_overlay()
            return
        left, top, mon_width, mon_height = geom
        try:
            mouse_x = float(state.get("mouse_offset_x", 0.0) or 0.0)
            mouse_y = float(state.get("mouse_offset_y", 0.0) or 0.0)
        except Exception:
            self.bullet_overlay.hide_overlay()
            return

        shared = dict(deep_get(self.current_profile_data, "app.shared", {}) or {})
        user_sens = max(1e-6, float(shared.get("game_sensitivity", 1.0) or 1.0))
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
        elif source == "gsi" and "weapon=" in message:
            self.shared_settings_tab.set_last_state(message.replace("[INFO] ", ""))

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
            self.shared_settings_tab.load_config(deep_get(self.current_profile_data, "app", {}))
            self.movement_tab.load_config(deep_get(self.current_profile_data, "components", {}))
            self.recoil_tab.load_config(deep_get(self.current_profile_data, "components.recoil", {}))
            self.pixel_trigger_tab.load_config(deep_get(self.current_profile_data, "components.pixel_trigger", {}))
            self.cv_trigger_tab.load_config(deep_get(self.current_profile_data, "components.cv_trigger", {}))
        finally:
            self._loading_profile = False

    def save_current_profile(self) -> None:
        self.profile_store.save_profile(self.current_profile_name, self.current_profile_data)
        self._append_log("app", f"Saved profile '{self.current_profile_name}'.")

    def apply_all_runtime(self) -> None:
        self._sync_current_profile_from_widgets()
        self.save_current_profile()
        self.runtime.configure_all(self.current_profile_data)
        self.runtime.configure_gsi(deep_get(self.current_profile_data, "app.gsi", {}))
        self.runtime.apply_enabled_states(self.current_profile_data)
        self._append_log("app", f"Applied profile '{self.current_profile_name}'.")

    def _sync_current_profile_from_widgets(self) -> None:
        shared_config = self.shared_settings_tab.extract_config()
        for key, value in shared_config.get("gsi", {}).items():
            deep_set(self.current_profile_data, f"app.gsi.{key}", value)
        for key, value in shared_config.get("shared", {}).items():
            deep_set(self.current_profile_data, f"app.shared.{key}", value)

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
            deep_set(self.current_profile_data, f"components.{name}", cfg)

    def _on_component_config_changed(self, component_name: str, config: dict[str, Any]) -> None:
        if self._loading_profile:
            return
        
        existing = deep_get(self.current_profile_data, f"components.{component_name}", {})
        if component_name == "cv_trigger":
            merged = deep_copy(config if isinstance(config, dict) else {})
        else:
            merged = _deep_merge_preserving_hidden(existing if isinstance(existing, dict) else {}, config)
        deep_set(self.current_profile_data, f"components.{component_name}", merged)
        self.profile_store.save_profile(self.current_profile_name, self.current_profile_data)
        self.runtime.restart_component(component_name, self.current_profile_data)

    def _on_shared_settings_changed(self) -> None:
        if self._loading_profile:
            return
        self._sync_current_profile_from_widgets()
        self.profile_store.save_profile(self.current_profile_name, self.current_profile_data)
        for name in ("bhop", "snap_tap", "counter_strafe", "recoil", "cv_trigger"):
            self.runtime.restart_component(name, self.current_profile_data)

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
        if confirm != QtWidgets.QMessageBox.Yes:
            return
        self.profile_store.delete_profile(self.current_profile_name)
        self.current_profile_name = "Default"
        self._refresh_profile_list()
        self.load_profile(self.current_profile_name)
        self.apply_all_runtime()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._closing = True
        self.bullet_overlay.hide_overlay()
        for component in self.runtime.components.values():
            component.set_status_callback(lambda *_args, **_kwargs: None)
        self.runtime.stop_all()
        super().closeEvent(event)
