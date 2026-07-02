from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from app.common import parse_json_text, pretty_json


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


class CVRuleEditor(QtWidgets.QFrame):
    changed = QtCore.Signal()
    remove_requested = QtCore.Signal(object)

    _KNOWN_KEYS = {
        "enabled",
        "activation",
        "allowed_weapons",
        "only_when_weapon",
        "auto_shoot",
        "spray_target_offset_enabled",
        "only_when_scoped_visual",
        "target_type",
        "AIM_MODE",
        "HEAD_OFFSET",
        "SNAP_DISTANCE",
        "SETTLE_FRAMES",
        "CLICK_HOLD_MS",
        "COOLDOWN_MS",
        "SENS_COEFF",
        "CROSS_X_THRESH",
        "CROSS_Y_THRESH_TOP",
        "CROSS_Y_THRESH_BOT",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setObjectName("cvRuleEditor")
        self.setStyleSheet("QFrame#cvRuleEditor { border: 1px solid #bbb; border-radius: 6px; }")
        self._suspend = False
        self._extra: dict[str, Any] = {}

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

        self.expand = QtWidgets.QToolButton(text="Details", checkable=True, checked=True)
        self.expand.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.expand.setArrowType(QtCore.Qt.DownArrow)
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
        outer.addWidget(self.content)
        form = QtWidgets.QFormLayout(self.content)
        form.setLabelAlignment(QtCore.Qt.AlignTop)

        self.activation_mode = QtWidgets.QComboBox()
        self.activation_mode.addItems(["always", "keyboard", "mouse"])
        self.activation_mode.currentTextChanged.connect(self._update_activation_visibility)
        self.activation_mode.currentTextChanged.connect(self._emit_change)
        form.addRow("Activation", self.activation_mode)

        self.activation_key = QtWidgets.QLineEdit()
        self.activation_key.setPlaceholderText("alt, shift, x, space ...")
        self.activation_key.editingFinished.connect(self._emit_change)
        form.addRow("Activation key", self.activation_key)

        self.activation_button = QtWidgets.QComboBox()
        self.activation_button.addItems(["left", "right", "middle", "x1", "x2"])
        self.activation_button.currentTextChanged.connect(self._emit_change)
        form.addRow("Activation mouse button", self.activation_button)

        self.allowed_weapons = QtWidgets.QLineEdit()
        self.allowed_weapons.setPlaceholderText("weapon_ak47, ak, m4a1s")
        self.allowed_weapons.editingFinished.connect(self._emit_change)
        form.addRow("Only for weapons", self.allowed_weapons)

        self.target_type = QtWidgets.QComboBox()
        self.target_type.addItem("Type 1 (T / C)", "type1")
        self.target_type.addItem("Type 2 (TH / CH)", "type2")
        self.target_type.addItem("Both types", "both")
        self.target_type.currentIndexChanged.connect(self._emit_change)
        form.addRow("Target type", self.target_type)

        self.only_when_scoped_visual = QtWidgets.QCheckBox()
        self.only_when_scoped_visual.stateChanged.connect(self._emit_change)
        form.addRow("Only when visually scoped", self.only_when_scoped_visual)

        self.auto_shoot = QtWidgets.QCheckBox()
        self.auto_shoot.stateChanged.connect(self._emit_change)
        form.addRow("Auto shoot", self.auto_shoot)

        self.spray_target_offset_enabled = QtWidgets.QCheckBox()
        self.spray_target_offset_enabled.stateChanged.connect(self._emit_change)
        form.addRow("Use recoil spray offset", self.spray_target_offset_enabled)

        self.aim_mode = QtWidgets.QComboBox()
        self.aim_mode.addItems(["head", "body"])
        self.aim_mode.currentTextChanged.connect(self._emit_change)
        form.addRow("Aim mode", self.aim_mode)

        self.head_offset = QtWidgets.QDoubleSpinBox()
        self.head_offset.setRange(-5.0, 5.0)
        self.head_offset.setDecimals(4)
        self.head_offset.setSingleStep(0.01)
        self.head_offset.valueChanged.connect(self._emit_change)
        form.addRow("Head offset", self.head_offset)

        self.snap_distance = QtWidgets.QSpinBox()
        self.snap_distance.setRange(0, 5000)
        self.snap_distance.valueChanged.connect(self._emit_change)
        form.addRow("Snap distance", self.snap_distance)

        self.settle_frames = QtWidgets.QSpinBox()
        self.settle_frames.setRange(0, 100)
        self.settle_frames.valueChanged.connect(self._emit_change)
        form.addRow("Settle frames", self.settle_frames)

        self.click_hold_ms = QtWidgets.QSpinBox()
        self.click_hold_ms.setRange(0, 5000)
        self.click_hold_ms.valueChanged.connect(self._emit_change)
        form.addRow("Click hold ms", self.click_hold_ms)

        self.cooldown_ms = QtWidgets.QSpinBox()
        self.cooldown_ms.setRange(0, 5000)
        self.cooldown_ms.valueChanged.connect(self._emit_change)
        form.addRow("Cooldown ms", self.cooldown_ms)

        self.sens_coeff = QtWidgets.QDoubleSpinBox()
        self.sens_coeff.setRange(0.0, 100.0)
        self.sens_coeff.setDecimals(4)
        self.sens_coeff.setSingleStep(0.01)
        self.sens_coeff.valueChanged.connect(self._emit_change)
        form.addRow("Sensitivity coeff", self.sens_coeff)

        self.cross_x_thresh = QtWidgets.QSpinBox()
        self.cross_x_thresh.setRange(0, 2000)
        self.cross_x_thresh.valueChanged.connect(self._emit_change)
        form.addRow("Cross X threshold", self.cross_x_thresh)

        self.cross_y_top = QtWidgets.QSpinBox()
        self.cross_y_top.setRange(-2000, 2000)
        self.cross_y_top.valueChanged.connect(self._emit_change)
        form.addRow("Cross Y top", self.cross_y_top)

        self.cross_y_bot = QtWidgets.QSpinBox()
        self.cross_y_bot.setRange(-2000, 2000)
        self.cross_y_bot.valueChanged.connect(self._emit_change)
        form.addRow("Cross Y bottom", self.cross_y_bot)

        self.extra_json = QtWidgets.QPlainTextEdit()
        self.extra_json.setFixedHeight(70)
        self.extra_json.textChanged.connect(self._emit_change)
        form.addRow("Extra JSON", self.extra_json)

        self._update_activation_visibility()
        self._update_summary()

    def _toggle_expanded(self, checked: bool) -> None:
        self.expand.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)
        self.content.setVisible(checked)

    def _sync_header_title(self) -> None:
        title = self.rule_name() or "Unnamed rule"
        self.expand.setText(title)
        self._update_summary()

    def _update_activation_visibility(self) -> None:
        mode = self.activation_mode.currentText().strip().lower()
        self.activation_key.setVisible(mode == "keyboard")
        self.activation_button.setVisible(mode == "mouse")
        form = self.content.layout()
        if isinstance(form, QtWidgets.QFormLayout):
            key_label = form.labelForField(self.activation_key)
            btn_label = form.labelForField(self.activation_button)
            if key_label is not None:
                key_label.setVisible(mode == "keyboard")
            if btn_label is not None:
                btn_label.setVisible(mode == "mouse")
        self._update_summary()

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
        type_text = f" | {self._target_type_value()}"
        scope_text = " | scoped only" if self.only_when_scoped_visual.isChecked() else ""
        spray_text = " | spray-align" if self.spray_target_offset_enabled.isChecked() else ""
        self.summary.setText(f"{name} — {activation}{weapon_text}{type_text}{scope_text}{shoot_text}{spray_text}")

    def rule_name(self) -> str:
        return self.name_edit.text().strip()

    def load_rule(self, name: str, rule: dict[str, Any]) -> None:
        self._suspend = True
        try:
            data = dict(rule or {})
            self._extra = {k: v for k, v in data.items() if k not in self._KNOWN_KEYS and k not in {"CLASSES", "only_when_scoped"}}
            self.name_edit.setText(name)
            self.enabled.setChecked(bool(data.get("enabled", True)))

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
            self.snap_distance.setValue(int(data.get("SNAP_DISTANCE", 50)))
            self.settle_frames.setValue(int(data.get("SETTLE_FRAMES", 2)))
            self.click_hold_ms.setValue(int(data.get("CLICK_HOLD_MS", 15)))
            self.cooldown_ms.setValue(int(data.get("COOLDOWN_MS", 250)))
            self.sens_coeff.setValue(float(data.get("SENS_COEFF", 1.0)))
            self.cross_x_thresh.setValue(int(data.get("CROSS_X_THRESH", 14)))
            self.cross_y_top.setValue(int(data.get("CROSS_Y_THRESH_TOP", 18)))
            self.cross_y_bot.setValue(int(data.get("CROSS_Y_THRESH_BOT", 32)))
            self.extra_json.setPlainText(pretty_json(self._extra))
            self._sync_header_title()
            self._update_activation_visibility()
        finally:
            self._suspend = False
            self._update_summary()

    def extract_rule(self) -> tuple[str, dict[str, Any]]:
        data = dict(self._extra)
        extra_raw = self.extra_json.toPlainText().strip()
        if extra_raw:
            parsed_extra = parse_json_text(extra_raw)
            if not isinstance(parsed_extra, dict):
                raise ValueError("Extra JSON must be an object/dict.")
            data.update(parsed_extra)

        data["enabled"] = self.enabled.isChecked()
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
        data["SNAP_DISTANCE"] = self.snap_distance.value()
        data["SETTLE_FRAMES"] = self.settle_frames.value()
        data["CLICK_HOLD_MS"] = self.click_hold_ms.value()
        data["COOLDOWN_MS"] = self.cooldown_ms.value()
        data["SENS_COEFF"] = self.sens_coeff.value()
        data.pop("CONFIDENCE", None)
        data.pop("IMG_SIZE", None)
        data["CROSS_X_THRESH"] = self.cross_x_thresh.value()
        data["CROSS_Y_THRESH_TOP"] = self.cross_y_top.value()
        data["CROSS_Y_THRESH_BOT"] = self.cross_y_bot.value()
        return self.rule_name(), data

    def _emit_change(self, *args) -> None:
        if self._suspend:
            return
        self._update_summary()
        self.changed.emit()
