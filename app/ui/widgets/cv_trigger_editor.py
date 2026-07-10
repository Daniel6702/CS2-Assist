from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from app.device_service import DeviceService

from .curve_editor import AimCurveEditor, load_curves

from .cv_rule_editor import CVRuleEditor, _infer_target_type_from_rule_ui


def _normalize_cv_trigger_config_for_ui(config: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(config or {})
    if not isinstance(cfg.get("configs"), dict):
        profiles = dict(cfg.get("profiles", {}))
        active_profile = str(cfg.get("active_profile", "pistol"))
        hold_mode = str(cfg.get("hold_mode", "alt")).strip().lower() or "alt"
        legacy = dict(profiles.get(active_profile, {}))
        if legacy:
            legacy.setdefault("enabled", True)
            legacy.setdefault("activation", {"device": "keyboard", "key": hold_mode})
            legacy.setdefault("auto_shoot", True)
            cfg["configs"] = {active_profile: legacy}
        else:
            cfg["configs"] = {}

    cfg.setdefault("use_gsi_opponent_side", False)
    cfg.setdefault("manual_target_side", "both")

    cfg["aim_curves"] = load_curves(cfg.get("aim_curves"))

    normalized_configs: dict[str, Any] = {}
    for raw_name, raw_item in dict(cfg.get("configs", {})).items():
        item = dict(raw_item or {})
        item["enabled"] = bool(item.get("enabled", True))
        activation = item.get("activation")
        if not isinstance(activation, dict):
            activation = {"device": "keyboard", "key": "alt"}
        mode = str(activation.get("mode", "")).strip().lower()
        if mode == "always":
            activation = {"mode": "always"}
        else:
            device = str(activation.get("device", "keyboard")).strip().lower() or "keyboard"
            if device == "mouse":
                activation = {"device": "mouse", "button": str(activation.get("button", "right"))}
            else:
                activation = {"device": "keyboard", "key": str(activation.get("key", "alt"))}
        item["activation"] = activation
        item["auto_shoot"] = bool(item.get("auto_shoot", True))
        item["spray_target_offset_enabled"] = bool(item.get("spray_target_offset_enabled", False))
        item["only_when_scoped_visual"] = bool(item.get("only_when_scoped_visual", item.get("only_when_scoped", False)))
        item["target_type"] = _infer_target_type_from_rule_ui(item)
        normalized_configs[str(raw_name)] = item
    cfg["configs"] = normalized_configs
    return cfg


class CVTriggerEditor(QtWidgets.QGroupBox):
    config_changed = QtCore.Signal(str, dict)

    def __init__(self, component_name: str, title: str, device_service: DeviceService, parent=None) -> None:
        super().__init__(title, parent)
        self.component_name = component_name
        self.device_service = device_service
        self._suspend = False
        self.rule_editors: list[CVRuleEditor] = []

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        top_row = QtWidgets.QHBoxLayout()
        top_row.setSpacing(12)
        outer.addLayout(top_row)

        status_group = QtWidgets.QGroupBox("Status")
        status_layout = QtWidgets.QFormLayout(status_group)
        status_layout.setLabelAlignment(QtCore.Qt.AlignTop)
        status_layout.setHorizontalSpacing(12)
        status_layout.setVerticalSpacing(6)
        top_row.addWidget(status_group, 1)

        self.enabled = QtWidgets.QCheckBox()
        self.enabled.stateChanged.connect(self._emit_change)
        status_layout.addRow("Enabled", self.enabled)

        self.runtime_status = QtWidgets.QLabel("Runtime: idle")
        self.runtime_status.setStyleSheet("color: #888; font-size: 11px;")
        status_layout.addRow("Runtime", self.runtime_status)

        target_group = QtWidgets.QGroupBox("Target Side")
        target_layout = QtWidgets.QFormLayout(target_group)
        target_layout.setLabelAlignment(QtCore.Qt.AlignTop)
        target_layout.setHorizontalSpacing(12)
        target_layout.setVerticalSpacing(6)
        top_row.addWidget(target_group, 1)

        self.use_gsi_opponent_side = QtWidgets.QCheckBox()
        self.use_gsi_opponent_side.stateChanged.connect(self._update_target_side_visibility)
        self.use_gsi_opponent_side.stateChanged.connect(self._emit_change)
        target_layout.addRow("Use GSI enemy side", self.use_gsi_opponent_side)

        self.manual_target_side = QtWidgets.QComboBox()
        self.manual_target_side.addItem("Terrorists", "terrorists")
        self.manual_target_side.addItem("Counter-Terrorists", "counter_terrorists")
        self.manual_target_side.addItem("Both", "both")
        self.manual_target_side.currentIndexChanged.connect(self._emit_change)
        target_layout.addRow("Manual target side", self.manual_target_side)
        self.manual_target_side_label = target_layout.labelForField(self.manual_target_side)

        capture_model_row = QtWidgets.QHBoxLayout()
        capture_model_row.setSpacing(12)
        outer.addLayout(capture_model_row)

        capture_group = QtWidgets.QGroupBox("Capture")
        capture_form = QtWidgets.QFormLayout(capture_group)
        capture_form.setLabelAlignment(QtCore.Qt.AlignTop)
        capture_form.setHorizontalSpacing(12)
        capture_form.setVerticalSpacing(6)
        capture_model_row.addWidget(capture_group, 1)

        self.monitor_top = QtWidgets.QSpinBox()
        self.monitor_top.setRange(-100000, 100000)
        self.monitor_top.valueChanged.connect(self._emit_change)
        self.monitor_left = QtWidgets.QSpinBox()
        self.monitor_left.setRange(-100000, 100000)
        self.monitor_left.valueChanged.connect(self._emit_change)
        self.monitor_width = QtWidgets.QSpinBox()
        self.monitor_width.setRange(1, 100000)
        self.monitor_width.valueChanged.connect(self._emit_change)
        self.monitor_height = QtWidgets.QSpinBox()
        self.monitor_height.setRange(1, 100000)
        self.monitor_height.valueChanged.connect(self._emit_change)
        monitor_row = QtWidgets.QWidget()
        monitor_layout = QtWidgets.QHBoxLayout(monitor_row)
        monitor_layout.setContentsMargins(0, 0, 0, 0)
        monitor_layout.addWidget(QtWidgets.QLabel("Top"))
        monitor_layout.addWidget(self.monitor_top)
        monitor_layout.addWidget(QtWidgets.QLabel("Left"))
        monitor_layout.addWidget(self.monitor_left)
        monitor_layout.addWidget(QtWidgets.QLabel("Width"))
        monitor_layout.addWidget(self.monitor_width)
        monitor_layout.addWidget(QtWidgets.QLabel("Height"))
        monitor_layout.addWidget(self.monitor_height)
        monitor_layout.addStretch(1)
        capture_form.addRow("Monitor", monitor_row)

        self.game_width = QtWidgets.QSpinBox()
        self.game_width.setRange(1, 100000)
        self.game_width.valueChanged.connect(self._emit_change)
        self.game_height = QtWidgets.QSpinBox()
        self.game_height.setRange(1, 100000)
        self.game_height.valueChanged.connect(self._emit_change)
        resolution_row = QtWidgets.QWidget()
        resolution_layout = QtWidgets.QHBoxLayout(resolution_row)
        resolution_layout.setContentsMargins(0, 0, 0, 0)
        resolution_layout.addWidget(QtWidgets.QLabel("Width"))
        resolution_layout.addWidget(self.game_width)
        resolution_layout.addWidget(QtWidgets.QLabel("Height"))
        resolution_layout.addWidget(self.game_height)
        resolution_layout.addStretch(1)
        capture_form.addRow("Game resolution", resolution_row)

        model_group = QtWidgets.QGroupBox("Model")
        model_form = QtWidgets.QFormLayout(model_group)
        model_form.setLabelAlignment(QtCore.Qt.AlignTop)
        model_form.setHorizontalSpacing(12)
        model_form.setVerticalSpacing(6)
        capture_model_row.addWidget(model_group, 1)

        self.model_path = QtWidgets.QLineEdit()
        self.model_path.editingFinished.connect(self._emit_change)
        model_form.addRow("Model path", self.model_path)

        tuning_row = QtWidgets.QHBoxLayout()
        tuning_row.setSpacing(12)
        outer.addLayout(tuning_row)

        detection_group = QtWidgets.QGroupBox("Detection & Smoothing")
        detection_form = QtWidgets.QFormLayout(detection_group)
        detection_form.setLabelAlignment(QtCore.Qt.AlignTop)
        detection_form.setHorizontalSpacing(12)
        detection_form.setVerticalSpacing(6)
        tuning_row.addWidget(detection_group, 1)

        self.inference_confidence = QtWidgets.QDoubleSpinBox()
        self.inference_confidence.setRange(0.0, 1.0)
        self.inference_confidence.setDecimals(4)
        self.inference_confidence.setSingleStep(0.01)
        self.inference_confidence.valueChanged.connect(self._emit_change)
        detection_form.addRow("Inference confidence", self.inference_confidence)

        self.inference_img_size = QtWidgets.QSpinBox()
        self.inference_img_size.setRange(32, 4096)
        self.inference_img_size.setSingleStep(32)
        self.inference_img_size.valueChanged.connect(self._emit_change)
        detection_form.addRow("Inference image size", self.inference_img_size)

        self.jitter_deadzone_px = QtWidgets.QDoubleSpinBox()
        self.jitter_deadzone_px.setRange(0.0, 100.0)
        self.jitter_deadzone_px.setDecimals(2)
        self.jitter_deadzone_px.setSingleStep(0.25)
        self.jitter_deadzone_px.valueChanged.connect(self._emit_change)
        detection_form.addRow("Jitter deadzone (px)", self.jitter_deadzone_px)

        self.near_smoothing_alpha = QtWidgets.QDoubleSpinBox()
        self.near_smoothing_alpha.setRange(0.01, 1.0)
        self.near_smoothing_alpha.setDecimals(3)
        self.near_smoothing_alpha.setSingleStep(0.05)
        self.near_smoothing_alpha.valueChanged.connect(self._emit_change)
        detection_form.addRow("Near smoothing alpha", self.near_smoothing_alpha)

        self.near_smoothing_radius_px = QtWidgets.QDoubleSpinBox()
        self.near_smoothing_radius_px.setRange(1.0, 500.0)
        self.near_smoothing_radius_px.setDecimals(1)
        self.near_smoothing_radius_px.setSingleStep(1.0)
        self.near_smoothing_radius_px.valueChanged.connect(self._emit_change)
        detection_form.addRow("Near smoothing radius (px)", self.near_smoothing_radius_px)

        prediction_group = QtWidgets.QGroupBox("Horizontal Prediction")
        prediction_form = QtWidgets.QFormLayout(prediction_group)
        prediction_form.setLabelAlignment(QtCore.Qt.AlignTop)
        prediction_form.setHorizontalSpacing(12)
        prediction_form.setVerticalSpacing(6)
        tuning_row.addWidget(prediction_group, 1)

        self.x_prediction_enabled = QtWidgets.QCheckBox()
        self.x_prediction_enabled.stateChanged.connect(self._emit_change)
        prediction_form.addRow("Predict horizontal motion", self.x_prediction_enabled)

        self.x_prediction_lead_ms = QtWidgets.QDoubleSpinBox()
        self.x_prediction_lead_ms.setRange(0.0, 250.0)
        self.x_prediction_lead_ms.setDecimals(1)
        self.x_prediction_lead_ms.setSingleStep(1.0)
        self.x_prediction_lead_ms.valueChanged.connect(self._emit_change)
        prediction_form.addRow("Prediction lead (ms)", self.x_prediction_lead_ms)

        self.x_prediction_history_ms = QtWidgets.QDoubleSpinBox()
        self.x_prediction_history_ms.setRange(10.0, 500.0)
        self.x_prediction_history_ms.setDecimals(1)
        self.x_prediction_history_ms.setSingleStep(5.0)
        self.x_prediction_history_ms.valueChanged.connect(self._emit_change)
        prediction_form.addRow("Prediction history (ms)", self.x_prediction_history_ms)

        self.x_prediction_damping = QtWidgets.QDoubleSpinBox()
        self.x_prediction_damping.setRange(0.0, 1.0)
        self.x_prediction_damping.setDecimals(3)
        self.x_prediction_damping.setSingleStep(0.05)
        self.x_prediction_damping.valueChanged.connect(self._emit_change)
        prediction_form.addRow("Prediction damping", self.x_prediction_damping)

        self.x_prediction_max_delta_px = QtWidgets.QDoubleSpinBox()
        self.x_prediction_max_delta_px.setRange(0.0, 500.0)
        self.x_prediction_max_delta_px.setDecimals(1)
        self.x_prediction_max_delta_px.setSingleStep(1.0)
        self.x_prediction_max_delta_px.valueChanged.connect(self._emit_change)
        prediction_form.addRow("Max predicted X shift (px)", self.x_prediction_max_delta_px)

        aim_curve_group = QtWidgets.QGroupBox("Aim Motion Curves")
        aim_curve_layout = QtWidgets.QVBoxLayout(aim_curve_group)
        aim_curve_layout.setContentsMargins(8, 8, 8, 8)
        self.aim_curve_editor = AimCurveEditor()
        self.aim_curve_editor.changed.connect(self._sync_rule_curve_options)
        self.aim_curve_editor.changed.connect(self._emit_change)
        aim_curve_layout.addWidget(self.aim_curve_editor)
        outer.addWidget(aim_curve_group)

        rule_header = QtWidgets.QHBoxLayout()
        label_col = QtWidgets.QVBoxLayout()
        title_lbl = QtWidgets.QLabel("Rules / configs")
        title_lbl.setStyleSheet("font-weight: 600;")
        label_col.addWidget(title_lbl)
        help_lbl = QtWidgets.QLabel("Each rule can be enabled separately, expanded, renamed, and matched to different activation inputs, target types, and weapons.")
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: #666;")
        label_col.addWidget(help_lbl)
        rule_header.addLayout(label_col, 1)

        self.add_rule_btn = QtWidgets.QPushButton("Add Rule")
        self.add_rule_btn.clicked.connect(self._on_add_rule_clicked)
        rule_header.addWidget(self.add_rule_btn)
        outer.addLayout(rule_header)

        self.rules_container = QtWidgets.QWidget()
        self.rules_layout = QtWidgets.QVBoxLayout(self.rules_container)
        self.rules_layout.setContentsMargins(0, 0, 0, 0)
        self.rules_layout.setSpacing(8)
        outer.addWidget(self.rules_container)
        outer.addStretch(1)
        self._update_target_side_visibility()

    def _update_target_side_visibility(self) -> None:
        manual_visible = not self.use_gsi_opponent_side.isChecked()
        self.manual_target_side.setVisible(manual_visible)
        self.manual_target_side_label.setVisible(manual_visible)

    def set_runtime_status(self, message: str) -> None:
        self.runtime_status.setText(f"Runtime status: {message}")

    def refresh_devices(self) -> None:
        return

    def load_config(self, config: dict[str, Any]) -> None:
        data = _normalize_cv_trigger_config_for_ui(config)
        self._suspend = True
        try:
            self.enabled.setChecked(bool(data.get("enabled", False)))
            self.model_path.setText(str(data.get("model_path", "")))
            monitor = data.get("monitor", {"top": 0, "left": 0, "width": 2560, "height": 1440})
            if not isinstance(monitor, dict):
                monitor = {"top": 0, "left": 0, "width": 2560, "height": 1440}
            self.monitor_top.setValue(int(monitor.get("top", 0) or 0))
            self.monitor_left.setValue(int(monitor.get("left", 0) or 0))
            self.monitor_width.setValue(max(1, int(monitor.get("width", 2560) or 2560)))
            self.monitor_height.setValue(max(1, int(monitor.get("height", 1440) or 1440)))

            game_resolution = data.get("game_resolution", {"width": 1600, "height": 1200})
            if not isinstance(game_resolution, dict):
                game_resolution = {"width": 1600, "height": 1200}
            self.game_width.setValue(max(1, int(game_resolution.get("width", 1600) or 1600)))
            self.game_height.setValue(max(1, int(game_resolution.get("height", 1200) or 1200)))
            self.use_gsi_opponent_side.setChecked(bool(data.get("use_gsi_opponent_side", False)))
            side_idx = self.manual_target_side.findData(str(data.get("manual_target_side", "both")))
            self.manual_target_side.setCurrentIndex(side_idx if side_idx >= 0 else self.manual_target_side.findData("both"))
            self.inference_confidence.setValue(float(data.get("inference_confidence", 0.15) or 0.15))
            self.inference_img_size.setValue(int(data.get("inference_img_size", 384) or 384))
            self.jitter_deadzone_px.setValue(float(data.get("jitter_deadzone_px", 2.0) or 2.0))
            self.near_smoothing_alpha.setValue(float(data.get("near_smoothing_alpha", 0.35) or 0.35))
            self.near_smoothing_radius_px.setValue(float(data.get("near_smoothing_radius_px", 32.0) or 32.0))
            self.x_prediction_enabled.setChecked(bool(data.get("x_prediction_enabled", False)))
            self.x_prediction_lead_ms.setValue(float(data.get("x_prediction_lead_ms", 28.0) or 28.0))
            self.x_prediction_history_ms.setValue(float(data.get("x_prediction_history_ms", 90.0) or 90.0))
            self.x_prediction_damping.setValue(float(data.get("x_prediction_damping", 0.35) or 0.35))
            self.x_prediction_max_delta_px.setValue(float(data.get("x_prediction_max_delta_px", 36.0) or 36.0))
            self.aim_curve_editor.load_curves(load_curves(data.get("aim_curves")))
            self._clear_rules()
            configs = dict(data.get("configs", {}))
            for name, rule in configs.items():
                self._add_rule_editor(name, dict(rule), emit_change=False)
            if not configs:
                self._add_rule_editor(
                    "pistol_alt",
                    {
                        "enabled": True,
                        "activation": {"device": "keyboard", "key": "alt"},
                        "auto_shoot": True,
                        "target_type": "both",
                        "only_when_scoped_visual": False,
                        "AIM_MODE": "head",
                        "HEAD_OFFSET": 0.12,
                        "SETTLE_FRAMES": 2,
                        "CLICK_HOLD_MS": 15,
                        "COOLDOWN_MS": 250,
                        "AIM_STRENGTH": 0.6,
                        "SNAP_DISTANCE": 200,
                        "AIM_CURVE_ID": "linear",
                        "MAX_AIM_SPEED_PX": 50,
                        "SMOOTHING_ALPHA": 0.0,
                        "NOISE_AMOUNT": 0.0,
                        "CROSS_X_THRESH": 14,
                        "CROSS_Y_THRESH_TOP": 18,
                        "CROSS_Y_THRESH_BOT": 32,
                    },
                    emit_change=False,
                )
            self._update_target_side_visibility()
        finally:
            self._suspend = False

    def extract_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {
            "enabled": self.enabled.isChecked(),
            "model_path": self.model_path.text().strip(),
            "monitor": {
                "top": self.monitor_top.value(),
                "left": self.monitor_left.value(),
                "width": self.monitor_width.value(),
                "height": self.monitor_height.value(),
            },
            "game_resolution": {
                "width": self.game_width.value(),
                "height": self.game_height.value(),
            },
            "use_gsi_opponent_side": self.use_gsi_opponent_side.isChecked(),
            "manual_target_side": str(self.manual_target_side.currentData() or "both"),
            "inference_confidence": self.inference_confidence.value(),
            "inference_img_size": self.inference_img_size.value(),
            "jitter_deadzone_px": self.jitter_deadzone_px.value(),
            "near_smoothing_alpha": self.near_smoothing_alpha.value(),
            "near_smoothing_radius_px": self.near_smoothing_radius_px.value(),
            "x_prediction_enabled": self.x_prediction_enabled.isChecked(),
            "x_prediction_lead_ms": self.x_prediction_lead_ms.value(),
            "x_prediction_history_ms": self.x_prediction_history_ms.value(),
            "x_prediction_damping": self.x_prediction_damping.value(),
            "x_prediction_max_delta_px": self.x_prediction_max_delta_px.value(),
            "configs": {},
        }

        seen: dict[str, int] = {}
        rules: dict[str, Any] = {}
        for idx, editor in enumerate(self.rule_editors, start=1):
            name, rule = editor.extract_rule()
            base_name = name or f"rule_{idx}"
            count = seen.get(base_name, 0)
            seen[base_name] = count + 1
            final_name = base_name if count == 0 else f"{base_name}_{count + 1}"
            rules[final_name] = rule
        config["configs"] = rules
        config["aim_curves"] = self.aim_curve_editor.extract_curves()
        return config

    def _clear_rules(self) -> None:
        while self.rule_editors:
            editor = self.rule_editors.pop()
            self.rules_layout.removeWidget(editor)
            editor.deleteLater()

    def _default_rule_payload(self) -> tuple[str, dict[str, Any]]:
        index = len(self.rule_editors) + 1
        return (
            f"rule_{index}",
            {
                "enabled": True,
                "activation": {"mode": "always"},
                "auto_shoot": True,
                "target_type": "both",
                "only_when_scoped_visual": False,
                "AIM_MODE": "head",
                "HEAD_OFFSET": 0.12,
                "SETTLE_FRAMES": 2,
                "CLICK_HOLD_MS": 15,
                "COOLDOWN_MS": 250,
                "AIM_STRENGTH": 0.6,
                "SNAP_DISTANCE": 200,
                "AIM_CURVE_ID": "linear",
                "MAX_AIM_SPEED_PX": 50,
                "SMOOTHING_ALPHA": 0.0,
                "NOISE_AMOUNT": 0.0,
                "CROSS_X_THRESH": 14,
                "CROSS_Y_THRESH_TOP": 18,
                "CROSS_Y_THRESH_BOT": 32,
            },
        )

    def _add_rule_editor(self, name: str, rule: dict[str, Any], emit_change: bool = True) -> None:
        editor = CVRuleEditor()
        editor.set_available_curves(self.aim_curve_editor.extract_curves())
        editor.load_rule(name, rule)
        editor.changed.connect(self._emit_change)
        editor.remove_requested.connect(self._remove_rule_editor)
        self.rule_editors.append(editor)
        self.rules_layout.addWidget(editor)
        if emit_change:
            self._emit_change()

    def _remove_rule_editor(self, editor: CVRuleEditor) -> None:
        if editor not in self.rule_editors:
            return
        self.rule_editors.remove(editor)
        self.rules_layout.removeWidget(editor)
        editor.deleteLater()
        self._emit_change()

    def _on_add_rule_clicked(self) -> None:
        name, rule = self._default_rule_payload()
        self._add_rule_editor(name, rule, emit_change=True)

    def _sync_rule_curve_options(self) -> None:
        curves = self.aim_curve_editor.extract_curves()
        for editor in self.rule_editors:
            editor.set_available_curves(curves)

    def _emit_change(self, *args) -> None:
        if self._suspend:
            return
        try:
            cfg = self.extract_config()
        except Exception:
            return
        self.config_changed.emit(self.component_name, cfg)
