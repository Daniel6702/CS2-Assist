from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from app.components.cv_trigger.curve_config import legacy_response_curve_to_id


_LEGACY_RULE_KEYS = {
    "RESPONSE_CURVE",
    "CURVE_INTENSITY",
    "CONSTANT_SPEED_PX",
    "ACCEL_BOOST",
    "ANTI_OVERSHOOT",
    "SENS_COEFF",
}


def _infer_target_type_from_rule_ui(item: dict[str, Any]) -> str:
    target_type = str(item.get("target_type", "") or "").strip().lower()
    if target_type in {"type1", "type2", "both"}:
        return target_type

    classes_value = item.get("CLASSES", None)
    if classes_value in (None, "", []):
        return "both"
    try:
        values = {int(v) for v in classes_value}
    except Exception:
        return "both"
    has_type1 = bool(values & {0, 2})
    has_type2 = bool(values & {1, 3})
    if has_type1 and has_type2:
        return "both"
    if has_type2:
        return "type2"
    return "type1"


def _scalar_aim_strength(value: Any, legacy_percent: bool) -> float:
    strength = float(value)
    if legacy_percent and strength > 1.0:
        return strength / 100.0
    return strength


class CVRuleEditor(QtWidgets.QFrame):
    changed = QtCore.Signal()
    remove_requested = QtCore.Signal(object)

    _KNOWN_KEYS = {
        "enabled",
        "priority",
        "activation",
        "allowed_weapons",
        "only_when_weapon",
        "auto_shoot",
        "auto_shoot_aim_cooldown_ms",
        "spray_target_offset_enabled",
        "only_when_scoped_visual",
        "target_type",
        "AIM_MODE",
        "HEAD_OFFSET",
        "BODY_KNEE_OFFSET",
        "SNAP_DISTANCE",
        "SETTLE_FRAMES",
        "CLICK_HOLD_MS",
        "COOLDOWN_MS",
        "AIM_STRENGTH",
        "AIM_CURVE_ID",
        "MAX_AIM_SPEED_PX",
        "SMOOTHING_ALPHA",
        "NOISE_AMOUNT",
        "AUTO_SHOOT_ZONE_WIDTH",
        "AUTO_SHOOT_ZONE_HEIGHT",
        "AUTO_SHOOT_ZONE_Y_POS",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setObjectName("cvRuleEditor")
        self.setStyleSheet("QFrame#cvRuleEditor { border: 1px solid #bbb; border-radius: 6px; }")
        self._suspend = False
        self._available_curves: dict[str, str] = {"linear": "Linear"}

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        header = QtWidgets.QHBoxLayout()
        self.enabled = QtWidgets.QCheckBox("Enabled")
        self.enabled.stateChanged.connect(self._emit_change)
        header.addWidget(self.enabled)

        header.addWidget(QtWidgets.QLabel("Name"))
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("Example: rifle_alt")
        self.name_edit.editingFinished.connect(self._sync_header_title)
        self.name_edit.editingFinished.connect(self._emit_change)
        header.addWidget(self.name_edit, 1)

        self.expand = QtWidgets.QToolButton()
        self.expand.setText("Details")
        self.expand.setCheckable(True)
        self.expand.setChecked(False)
        self.expand.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.expand.setArrowType(QtCore.Qt.ArrowType.RightArrow)
        self.expand.clicked.connect(self._toggle_expanded)
        header.addWidget(self.expand)

        self.remove_btn = QtWidgets.QPushButton("Remove")
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        header.addWidget(self.remove_btn)

        outer.addLayout(header)

        self.summary = QtWidgets.QLabel("")
        self.summary.setStyleSheet("color: #666;")
        self.summary.setWordWrap(True)
        outer.addWidget(self.summary)

        self.content = QtWidgets.QWidget()
        self.content.setVisible(False)
        outer.addWidget(self.content)
        content_layout = QtWidgets.QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        top_row = QtWidgets.QHBoxLayout()
        top_row.setSpacing(10)
        content_layout.addLayout(top_row)

        activation_group = QtWidgets.QGroupBox("Activation")
        activation_form = QtWidgets.QFormLayout(activation_group)
        activation_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        activation_form.setHorizontalSpacing(12)
        activation_form.setVerticalSpacing(6)
        top_row.addWidget(activation_group, 1)

        self.activation_mode = QtWidgets.QComboBox()
        self.activation_mode.addItems(["always", "keyboard", "mouse"])
        self.activation_mode.currentTextChanged.connect(self._update_activation_visibility)
        self.activation_mode.currentTextChanged.connect(self._emit_change)
        activation_form.addRow("Mode", self.activation_mode)

        self.activation_key = QtWidgets.QLineEdit()
        self.activation_key.setPlaceholderText("alt, shift, x, space ...")
        self.activation_key.editingFinished.connect(self._emit_change)
        activation_form.addRow("Key", self.activation_key)
        self.activation_key_label = activation_form.labelForField(self.activation_key)

        self.activation_button = QtWidgets.QComboBox()
        self.activation_button.addItems(["left", "right", "middle", "x1", "x2"])
        self.activation_button.currentTextChanged.connect(self._emit_change)
        activation_form.addRow("Mouse button", self.activation_button)
        self.activation_button_label = activation_form.labelForField(self.activation_button)

        self.priority = QtWidgets.QSpinBox()
        self.priority.setRange(-2_147_483_648, 2_147_483_647)
        self.priority.setToolTip("Higher active priority suppresses lower-priority rules. Same priority rules combine.")
        self.priority.valueChanged.connect(self._emit_change)
        activation_form.addRow("Priority", self.priority)

        filter_group = QtWidgets.QGroupBox("Target & Weapon Filters")
        filter_form = QtWidgets.QFormLayout(filter_group)
        filter_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        filter_form.setHorizontalSpacing(12)
        filter_form.setVerticalSpacing(6)
        top_row.addWidget(filter_group, 2)

        self.allowed_weapons = QtWidgets.QLineEdit()
        self.allowed_weapons.setPlaceholderText("weapon_ak47, ak, m4a1s")
        self.allowed_weapons.editingFinished.connect(self._emit_change)
        filter_form.addRow("Only for weapons", self.allowed_weapons)

        self.target_type = QtWidgets.QComboBox()
        self.target_type.addItem("Type 1 (T / C)", "type1")
        self.target_type.addItem("Type 2 (TH / CH)", "type2")
        self.target_type.addItem("Both types", "both")
        self.target_type.currentIndexChanged.connect(self._emit_change)
        filter_form.addRow("Target type", self.target_type)

        self.only_when_scoped_visual = QtWidgets.QCheckBox()
        self.only_when_scoped_visual.stateChanged.connect(self._emit_change)
        filter_form.addRow("Visually scoped only", self.only_when_scoped_visual)

        tuning_row1 = QtWidgets.QHBoxLayout()
        tuning_row1.setSpacing(10)
        content_layout.addLayout(tuning_row1)

        targeting_group = QtWidgets.QGroupBox("Targeting")
        targeting_form = QtWidgets.QFormLayout(targeting_group)
        targeting_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        targeting_form.setHorizontalSpacing(12)
        targeting_form.setVerticalSpacing(6)
        tuning_row1.addWidget(targeting_group, 1)

        self.aim_mode = QtWidgets.QComboBox()
        self.aim_mode.addItems(["head", "body"])
        self.aim_mode.currentTextChanged.connect(self._emit_change)
        targeting_form.addRow("Aim mode", self.aim_mode)

        self.head_offset = QtWidgets.QDoubleSpinBox()
        self.head_offset.setRange(-5.0, 5.0)
        self.head_offset.setDecimals(4)
        self.head_offset.setSingleStep(0.01)
        self.head_offset.valueChanged.connect(self._emit_change)
        targeting_form.addRow("Head offset", self.head_offset)

        self.body_knee_offset = QtWidgets.QDoubleSpinBox()
        self.body_knee_offset.setRange(0.0, 1.0)
        self.body_knee_offset.setDecimals(4)
        self.body_knee_offset.setSingleStep(0.01)
        self.body_knee_offset.setToolTip(
            "Vertical fraction from top of bounding box to aim at in body mode.\n"
            "0.50 = centre, 0.00 = top, 1.00 = bottom."
        )
        self.body_knee_offset.valueChanged.connect(self._emit_change)
        targeting_form.addRow("Body knee offset", self.body_knee_offset)

        self.spray_target_offset_enabled = QtWidgets.QCheckBox()
        self.spray_target_offset_enabled.stateChanged.connect(self._emit_change)
        targeting_form.addRow("Use recoil spray offset", self.spray_target_offset_enabled)

        self.auto_shoot_aim_cooldown_ms = QtWidgets.QSpinBox()
        self.auto_shoot_aim_cooldown_ms.setRange(0, 5000)
        self.auto_shoot_aim_cooldown_ms.setSuffix(" ms")
        self.auto_shoot_aim_cooldown_ms.setToolTip(
            "After a kill is detected via GSI, disable aim assist (mouse movement) "
            "for this rule for this many ms.  0 = disabled."
        )
        self.auto_shoot_aim_cooldown_ms.valueChanged.connect(self._emit_change)
        targeting_form.addRow("Kill cooldown", self.auto_shoot_aim_cooldown_ms)

        timing_group = QtWidgets.QGroupBox("Auto Shoot")
        timing_layout = QtWidgets.QHBoxLayout(timing_group)
        timing_layout.setContentsMargins(8, 8, 8, 8)
        timing_layout.setSpacing(12)
        timing_form = QtWidgets.QFormLayout()
        timing_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        timing_form.setHorizontalSpacing(12)
        timing_form.setVerticalSpacing(6)
        threshold_form = QtWidgets.QFormLayout()
        threshold_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        threshold_form.setHorizontalSpacing(12)
        threshold_form.setVerticalSpacing(6)
        timing_layout.addLayout(timing_form, 1)
        timing_layout.addLayout(threshold_form, 1)
        tuning_row1.addWidget(timing_group, 1)

        # ── Aim Tuning (new configurable box) ────────────────────────────
        aim_tuning_group = QtWidgets.QGroupBox("Aim Tuning")
        aim_tuning_form = QtWidgets.QFormLayout(aim_tuning_group)
        aim_tuning_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        aim_tuning_form.setHorizontalSpacing(12)
        aim_tuning_form.setVerticalSpacing(6)
        content_layout.addWidget(aim_tuning_group)

        self.aim_strength = QtWidgets.QDoubleSpinBox()
        self.aim_strength.setRange(0.0, 100.0)
        self.aim_strength.setDecimals(3)
        self.aim_strength.setSingleStep(0.1)
        self.aim_strength.setToolTip("Scalar aim assist power. 0 = off, 0.5 = moderate, 1.0 = full, values above 1 increase speed.")
        self.aim_strength.valueChanged.connect(self._emit_change)
        aim_tuning_form.addRow("Aim Strength", self.aim_strength)

        self.snap_distance = QtWidgets.QSpinBox()
        self.snap_distance.setRange(0, 5000)
        self.snap_distance.setSuffix(" px")
        self.snap_distance.setToolTip("Maximum distance (in pixels) at which aim assist engages.")
        self.snap_distance.valueChanged.connect(self._emit_change)
        aim_tuning_form.addRow("Snap Distance", self.snap_distance)

        self.aim_curve_id = QtWidgets.QComboBox()
        self.aim_curve_id.setToolTip("Named curve from the global Aim Motion Curves library.")
        self.aim_curve_id.currentIndexChanged.connect(self._emit_change)
        aim_tuning_form.addRow("Aim Curve", self.aim_curve_id)
        self._rebuild_curve_selector("linear")

        self.max_aim_speed_px = QtWidgets.QSpinBox()
        self.max_aim_speed_px.setRange(0, 5000)
        self.max_aim_speed_px.setSuffix(" px")
        self.max_aim_speed_px.setToolTip("Maximum movement speed before the selected curve and strength scaling are applied.")
        self.max_aim_speed_px.valueChanged.connect(self._emit_change)
        aim_tuning_form.addRow("Max Aim Speed", self.max_aim_speed_px)

        self.smoothing_alpha = QtWidgets.QDoubleSpinBox()
        self.smoothing_alpha.setRange(0.0, 1.0)
        self.smoothing_alpha.setDecimals(3)
        self.smoothing_alpha.setSingleStep(0.05)
        self.smoothing_alpha.setToolTip(
            "Per-rule smoothing of aim movement.\n"
            "0 = instant (no smoothing), 1 = maximum smoothing.\n"
            "Works together with global Near Smoothing in Detection & Smoothing."
        )
        self.smoothing_alpha.valueChanged.connect(self._emit_change)
        aim_tuning_form.addRow("Smoothing", self.smoothing_alpha)

        self.noise_amount = QtWidgets.QDoubleSpinBox()
        self.noise_amount.setRange(0.0, 20.0)
        self.noise_amount.setDecimals(2)
        self.noise_amount.setSingleStep(0.25)
        self.noise_amount.setSuffix(" px")
        self.noise_amount.setToolTip(
            "Adds random jitter to aim movement for more natural feel.\n"
            "0 = disabled.  Keep small (1–5 px) for subtle human-like wobble."
        )
        self.noise_amount.valueChanged.connect(self._emit_change)
        aim_tuning_form.addRow("Noise Amount", self.noise_amount)

        self.auto_shoot = QtWidgets.QCheckBox()
        self.auto_shoot.stateChanged.connect(self._emit_change)
        timing_form.addRow("Enable", self.auto_shoot)

        self.settle_frames = QtWidgets.QSpinBox()
        self.settle_frames.setRange(0, 100)
        self.settle_frames.valueChanged.connect(self._emit_change)
        timing_form.addRow("Settle frames", self.settle_frames)

        self.click_hold_ms = QtWidgets.QSpinBox()
        self.click_hold_ms.setRange(0, 5000)
        self.click_hold_ms.valueChanged.connect(self._emit_change)
        timing_form.addRow("Click hold ms", self.click_hold_ms)

        self.cooldown_ms = QtWidgets.QSpinBox()
        self.cooldown_ms.setRange(0, 5000)
        self.cooldown_ms.valueChanged.connect(self._emit_change)
        timing_form.addRow("Cooldown ms", self.cooldown_ms)

        self.auto_shoot_zone_width = QtWidgets.QSpinBox()
        self.auto_shoot_zone_width.setRange(0, 500)
        self.auto_shoot_zone_width.setSuffix(" px")
        self.auto_shoot_zone_width.setToolTip(
            "Total width of the auto-shoot trigger zone.\n"
            "The zone is centred horizontally on the target detection box."
        )
        self.auto_shoot_zone_width.valueChanged.connect(self._emit_change)
        threshold_form.addRow("Zone width", self.auto_shoot_zone_width)

        self.auto_shoot_zone_height = QtWidgets.QSpinBox()
        self.auto_shoot_zone_height.setRange(0, 500)
        self.auto_shoot_zone_height.setSuffix(" px")
        self.auto_shoot_zone_height.setToolTip(
            "Total height of the auto-shoot trigger zone.\n"
            "The zone is centred vertically at the Y position below."
        )
        self.auto_shoot_zone_height.valueChanged.connect(self._emit_change)
        threshold_form.addRow("Zone height", self.auto_shoot_zone_height)

        self.auto_shoot_zone_y_pos = QtWidgets.QDoubleSpinBox()
        self.auto_shoot_zone_y_pos.setRange(0.0, 1.0)
        self.auto_shoot_zone_y_pos.setDecimals(3)
        self.auto_shoot_zone_y_pos.setSingleStep(0.05)
        self.auto_shoot_zone_y_pos.setToolTip(
            "Vertical position of the zone centre on the target detection box.\n"
            "0.00 = top of the bounding box, 0.50 = centre, 1.00 = bottom.\n"
            "0.30–0.40 is a good range for head / upper-chest targeting."
        )
        self.auto_shoot_zone_y_pos.valueChanged.connect(self._emit_change)
        threshold_form.addRow("Zone Y position", self.auto_shoot_zone_y_pos)

        input_row_height = self.aim_mode.sizeHint().height()
        for checkbox in (
            self.only_when_scoped_visual,
            self.spray_target_offset_enabled,
            self.auto_shoot,
        ):
            checkbox.setMinimumHeight(input_row_height)

        self._update_activation_visibility()
        self._update_summary()

    def _toggle_expanded(self, checked: bool) -> None:
        self.expand.setArrowType(QtCore.Qt.ArrowType.DownArrow if checked else QtCore.Qt.ArrowType.RightArrow)
        self.content.setVisible(checked)

    def _sync_header_title(self) -> None:
        title = self.rule_name() or "Unnamed rule"
        self.expand.setText(title)
        self._update_summary()

    def _update_activation_visibility(self) -> None:
        mode = self.activation_mode.currentText().strip().lower()
        self.activation_key.setVisible(mode == "keyboard")
        self.activation_button.setVisible(mode == "mouse")
        self.activation_key_label.setVisible(mode == "keyboard")
        self.activation_button_label.setVisible(mode == "mouse")
        self._update_summary()

    def set_available_curves(self, curves: dict[str, Any]) -> None:
        current = str(self.aim_curve_id.currentData() or self.aim_curve_id.currentText() or "linear")
        labels: dict[str, str] = {}
        for curve_id, curve in curves.items():
            if not isinstance(curve_id, str) or not curve_id.strip():
                continue
            label = curve_id
            if isinstance(curve, dict):
                label = str(curve.get("label", curve_id) or curve_id)
            labels[curve_id] = label
        if not labels:
            labels = {"linear": "Linear"}
        self._available_curves = labels
        self._rebuild_curve_selector(current)

    def _rebuild_curve_selector(self, selected_curve_id: str) -> None:
        was_suspended = self._suspend
        self._suspend = True
        try:
            self.aim_curve_id.clear()
            for curve_id, label in self._available_curves.items():
                self.aim_curve_id.addItem(label, curve_id)
            self._set_curve_selection(selected_curve_id)
        finally:
            self._suspend = was_suspended

    def _set_curve_selection(self, curve_id: str) -> None:
        idx = self.aim_curve_id.findData(curve_id)
        if idx < 0:
            idx = self.aim_curve_id.findData("linear")
        self.aim_curve_id.setCurrentIndex(idx if idx >= 0 else 0)

    def _target_type_value(self) -> str:
        return str(self.target_type.currentData() or "both")

    def _set_target_type_value(self, value: str) -> None:
        idx = self.target_type.findData(value)
        self.target_type.setCurrentIndex(idx if idx >= 0 else self.target_type.findData("both"))

    def _update_summary(self) -> None:
        name = self.rule_name() or "Unnamed rule"
        mode = self.activation_mode.currentText().strip().lower()
        if mode == "always":
            activation = "always active"
        elif mode == "mouse":
            activation = f"hold mouse {self.activation_button.currentText()}"
        else:
            activation = f"hold key {self.activation_key.text().strip() or 'alt'}"
        weapons = self.allowed_weapons.text().strip()
        weapon_text = f" | weapons: {weapons}" if weapons else " | any weapon"
        shoot_text = " | auto shoot" if self.auto_shoot.isChecked() else " | aim only"
        priority_text = f" | priority {self.priority.value()}"
        aim_cd = self.auto_shoot_aim_cooldown_ms.value()
        aim_cd_text = f" | kill cd {aim_cd}ms" if aim_cd > 0 else ""
        zw = self.auto_shoot_zone_width.value()
        zh = self.auto_shoot_zone_height.value()
        zy = self.auto_shoot_zone_y_pos.value()
        zone_text = f" | zone {zw}×{zh} @ y={zy:.2f}" if self.auto_shoot.isChecked() else ""
        type_text = f" | {self._target_type_value()}"
        scope_text = " | scoped only" if self.only_when_scoped_visual.isChecked() else ""
        spray_text = " | spray-align" if self.spray_target_offset_enabled.isChecked() else ""
        self.summary.setText(f"{name} — {activation}{priority_text}{weapon_text}{type_text}{scope_text}{shoot_text}{spray_text}{aim_cd_text}{zone_text}")

    def rule_name(self) -> str:
        return self.name_edit.text().strip()

    def load_rule(self, name: str, rule: dict[str, Any]) -> None:
        self._suspend = True
        try:
            data = dict(rule or {})
            self.name_edit.setText(name)
            self.enabled.setChecked(bool(data.get("enabled", True)))
            try:
                priority = int(data.get("priority", 0) or 0)
            except (TypeError, ValueError):
                priority = 0
            self.priority.setValue(priority)

            activation = dict(data.get("activation", {}))
            if str(activation.get("mode", "")).strip().lower() == "always":
                self.activation_mode.setCurrentText("always")
            elif str(activation.get("device", "keyboard")).strip().lower() == "mouse":
                self.activation_mode.setCurrentText("mouse")
                self.activation_button.setCurrentText(str(activation.get("button", "right")))
            else:
                self.activation_mode.setCurrentText("keyboard")
                self.activation_key.setText(str(activation.get("key", "alt")))

            allowed = data.get("allowed_weapons", data.get("only_when_weapon", []))
            if isinstance(allowed, str):
                allowed_text = allowed
            elif isinstance(allowed, (list, tuple, set)):
                allowed_text = ", ".join(str(item) for item in allowed)
            else:
                allowed_text = ""
            self.allowed_weapons.setText(allowed_text)

            self._set_target_type_value(_infer_target_type_from_rule_ui(data))
            self.only_when_scoped_visual.setChecked(bool(data.get("only_when_scoped_visual", data.get("only_when_scoped", False))))
            self.auto_shoot.setChecked(bool(data.get("auto_shoot", True)))
            self.spray_target_offset_enabled.setChecked(bool(data.get("spray_target_offset_enabled", False)))
            self.aim_mode.setCurrentText(str(data.get("AIM_MODE", "head")))
            self.head_offset.setValue(float(data.get("HEAD_OFFSET", 0.12)))
            self.body_knee_offset.setValue(float(data.get("BODY_KNEE_OFFSET", 0.50)))
            self.settle_frames.setValue(int(data.get("SETTLE_FRAMES", 2)))
            self.click_hold_ms.setValue(int(data.get("CLICK_HOLD_MS", 15)))
            self.cooldown_ms.setValue(int(data.get("COOLDOWN_MS", 250)))
            self.auto_shoot_aim_cooldown_ms.setValue(int(data.get("auto_shoot_aim_cooldown_ms", 0)))
            canonical_shape = "AIM_CURVE_ID" in data or "MAX_AIM_SPEED_PX" in data
            legacy_percent = (not canonical_shape) or bool(_LEGACY_RULE_KEYS & set(data))
            self.aim_strength.setValue(_scalar_aim_strength(data.get("AIM_STRENGTH", data.get("SENS_COEFF", 0.5)), legacy_percent))
            self.snap_distance.setValue(int(data.get("SNAP_DISTANCE", 200)))
            curve_id = str(data.get("AIM_CURVE_ID", legacy_response_curve_to_id(data.get("RESPONSE_CURVE"))))
            self._set_curve_selection(curve_id)
            self.max_aim_speed_px.setValue(int(data.get("MAX_AIM_SPEED_PX", data.get("CONSTANT_SPEED_PX", 50))))
            self.smoothing_alpha.setValue(float(data.get("SMOOTHING_ALPHA", 0.0)))
            self.noise_amount.setValue(float(data.get("NOISE_AMOUNT", 0.0)))
            self.auto_shoot_zone_width.setValue(int(data.get("AUTO_SHOOT_ZONE_WIDTH", 28)))
            self.auto_shoot_zone_height.setValue(int(data.get("AUTO_SHOOT_ZONE_HEIGHT", 36)))
            self.auto_shoot_zone_y_pos.setValue(float(data.get("AUTO_SHOOT_ZONE_Y_POS", 0.35)))
            self._sync_header_title()
            self._update_activation_visibility()
        finally:
            self._suspend = False
            self._update_summary()

    def extract_rule(self) -> tuple[str, dict[str, Any]]:
        data: dict[str, Any] = {}

        data["enabled"] = self.enabled.isChecked()
        data["priority"] = self.priority.value()
        mode = self.activation_mode.currentText().strip().lower()
        if mode == "always":
            data["activation"] = {"mode": "always"}
        elif mode == "mouse":
            data["activation"] = {"device": "mouse", "button": self.activation_button.currentText()}
        else:
            data["activation"] = {"device": "keyboard", "key": self.activation_key.text().strip() or "alt"}

        weapon_text = self.allowed_weapons.text().strip()
        if weapon_text:
            data["allowed_weapons"] = [item.strip() for item in weapon_text.split(",") if item.strip()]
        else:
            data.pop("allowed_weapons", None)
            data.pop("only_when_weapon", None)

        data["target_type"] = self._target_type_value()
        data.pop("CLASSES", None)
        data["only_when_scoped_visual"] = self.only_when_scoped_visual.isChecked()
        data.pop("only_when_scoped", None)
        data["auto_shoot"] = self.auto_shoot.isChecked()
        data["spray_target_offset_enabled"] = self.spray_target_offset_enabled.isChecked()
        data.pop("spray_target_offset_scale", None)
        data["AIM_MODE"] = self.aim_mode.currentText()
        data["HEAD_OFFSET"] = self.head_offset.value()
        data["BODY_KNEE_OFFSET"] = self.body_knee_offset.value()
        data["SNAP_DISTANCE"] = self.snap_distance.value()
        data["SETTLE_FRAMES"] = self.settle_frames.value()
        data["CLICK_HOLD_MS"] = self.click_hold_ms.value()
        data["COOLDOWN_MS"] = self.cooldown_ms.value()
        data["auto_shoot_aim_cooldown_ms"] = self.auto_shoot_aim_cooldown_ms.value()
        data["AIM_STRENGTH"] = self.aim_strength.value()
        data["SNAP_DISTANCE"] = self.snap_distance.value()
        data["AIM_CURVE_ID"] = str(self.aim_curve_id.currentData() or "linear")
        data["MAX_AIM_SPEED_PX"] = self.max_aim_speed_px.value()
        data["SMOOTHING_ALPHA"] = self.smoothing_alpha.value()
        data["NOISE_AMOUNT"] = self.noise_amount.value()
        data.pop("SENS_COEFF", None)
        data.pop("CONFIDENCE", None)
        data.pop("IMG_SIZE", None)
        data["AUTO_SHOOT_ZONE_WIDTH"] = self.auto_shoot_zone_width.value()
        data["AUTO_SHOOT_ZONE_HEIGHT"] = self.auto_shoot_zone_height.value()
        data["AUTO_SHOOT_ZONE_Y_POS"] = self.auto_shoot_zone_y_pos.value()
        return self.rule_name(), data

    def _emit_change(self, *args) -> None:
        if self._suspend:
            return
        self._update_summary()
        self.changed.emit()
