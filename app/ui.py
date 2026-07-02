from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from app.common import deep_copy, deep_get, deep_set, parse_json_text, pretty_json
from app.device_service import DeviceService
from app.profile_store import ProfileStore
from app.runtime import RuntimeManager


class LogBridge(QtCore.QObject):
    message = QtCore.Signal(str, str)


class BulletImpactOverlay(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__(None)
        self._diameter = 12
        self._opacity = 0.9

        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.X11BypassWindowManagerHint
            | QtCore.Qt.WindowTransparentForInput
            | QtCore.Qt.WindowDoesNotAcceptFocus
            | QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self._apply_shape()

        self._raise_timer = QtCore.QTimer(self)
        self._raise_timer.timeout.connect(self._keep_on_top)
        self._raise_timer.start(250)

        self.hide()

    def _apply_shape(self) -> None:
        self.setFixedSize(self._diameter, self._diameter)
        self.setMask(QtGui.QRegion(0, 0, self._diameter, self._diameter, QtGui.QRegion.RegionType.Ellipse))

    def configure(self, diameter_px: int, opacity: float) -> None:
        diameter_px = max(4, int(diameter_px))
        opacity = max(0.05, min(1.0, float(opacity)))
        changed = diameter_px != self._diameter
        self._diameter = diameter_px
        self._opacity = opacity
        if changed:
            self._apply_shape()
            self.update()

    def _keep_on_top(self) -> None:
        if self.isVisible():
            self.raise_()

    def show_point(self, center_x: float, center_y: float) -> None:
        x = int(round(center_x - self._diameter / 2))
        y = int(round(center_y - self._diameter / 2))
        self.move(x, y)
        if not self.isVisible():
            self.show()
        self.raise_()
        self.update()

    def hide_overlay(self) -> None:
        self.hide()

    def paintEvent(self, event) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QtCore.Qt.NoPen)
        alpha = max(1, min(255, int(round(self._opacity * 255))))
        painter.setBrush(QtGui.QColor(255, 0, 0, alpha))
        painter.drawEllipse(0, 0, self._diameter, self._diameter)



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


def _deep_merge_preserving_hidden(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = deep_copy(base) if isinstance(base, dict) else {}
    for key, value in (update or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_preserving_hidden(merged[key], value)
        else:
            merged[key] = value
    return merged


class CollapsibleBox(QtWidgets.QWidget):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.toggle = QtWidgets.QToolButton(text=title, checkable=True, checked=False)
        self.toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(QtCore.Qt.RightArrow)
        self.toggle.clicked.connect(self._on_toggled)

        self.content = QtWidgets.QWidget()
        self.content.setVisible(False)
        self.content_layout = QtWidgets.QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(12, 8, 0, 8)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)

    def _on_toggled(self, checked: bool) -> None:
        self.toggle.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)
        self.content.setVisible(checked)


class ComponentEditor(QtWidgets.QGroupBox):
    config_changed = QtCore.Signal(str, dict)

    def __init__(self, component_name: str, title: str, schema: list[dict[str, Any]], device_service: DeviceService, parent=None) -> None:
        super().__init__(title, parent)
        self.component_name = component_name
        self.schema = schema
        self.device_service = device_service
        self.widgets: dict[str, QtWidgets.QWidget] = {}
        self._suspend = False

        outer = QtWidgets.QVBoxLayout(self)

        self.runtime_status = QtWidgets.QLabel("Runtime status: idle")
        self.runtime_status.setWordWrap(True)
        self.runtime_status.setStyleSheet("color: #666;")
        outer.addWidget(self.runtime_status)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignTop)
        outer.addLayout(form)

        for spec in schema:
            label = spec["label"]
            path = spec["path"]
            widget = self._create_widget(spec)
            self.widgets[path] = widget
            form.addRow(label, widget)

    def set_runtime_status(self, message: str) -> None:
        self.runtime_status.setText(f"Runtime status: {message}")

    def _create_widget(self, spec: dict[str, Any]) -> QtWidgets.QWidget:
        kind = spec["kind"]
        if kind == "bool":
            widget = QtWidgets.QCheckBox()
            widget.stateChanged.connect(self._emit_change)
            return widget
        if kind == "int":
            widget = QtWidgets.QSpinBox()
            widget.setRange(spec.get("min", -1_000_000), spec.get("max", 1_000_000))
            widget.valueChanged.connect(self._emit_change)
            return widget
        if kind == "float":
            widget = QtWidgets.QDoubleSpinBox()
            widget.setDecimals(spec.get("decimals", 4))
            widget.setRange(spec.get("min", -1_000_000.0), spec.get("max", 1_000_000.0))
            widget.setSingleStep(spec.get("step", 0.1))
            widget.valueChanged.connect(self._emit_change)
            return widget
        if kind == "choice":
            widget = QtWidgets.QComboBox()
            widget.addItems(spec.get("choices", []))
            widget.currentTextChanged.connect(self._emit_change)
            return widget
        if kind == "line":
            widget = QtWidgets.QLineEdit()
            widget.editingFinished.connect(self._emit_change)
            return widget
        if kind == "device":
            widget = QtWidgets.QComboBox()
            widget.currentTextChanged.connect(self._emit_change)
            return widget
        if kind == "json":
            widget = QtWidgets.QPlainTextEdit()
            widget.setTabChangesFocus(True)
            widget.setFixedHeight(spec.get("height", 140))
            widget.textChanged.connect(self._emit_change)
            return widget
        raise ValueError(f"Unsupported widget kind: {kind}")

    def refresh_devices(self) -> None:
        devices = self.device_service.list_keyboards()
        for spec in self.schema:
            if spec["kind"] != "device":
                continue
            combo = self.widgets[spec["path"]]
            assert isinstance(combo, QtWidgets.QComboBox)
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Auto-detect", "")
            for item in devices:
                combo.addItem(item.label, item.path)
            index = combo.findData(current)
            if index >= 0:
                combo.setCurrentIndex(index)
            combo.blockSignals(False)

    def load_config(self, config: dict[str, Any]) -> None:
        self._suspend = True
        try:
            for spec in self.schema:
                path = spec["path"]
                kind = spec["kind"]
                value = deep_get(config, path)
                if value is None and "default" in spec:
                    value = spec["default"]
                widget = self.widgets[path]
                if kind == "bool":
                    assert isinstance(widget, QtWidgets.QCheckBox)
                    widget.setChecked(bool(value))
                elif kind == "int":
                    assert isinstance(widget, QtWidgets.QSpinBox)
                    widget.setValue(int(value or 0))
                elif kind == "float":
                    assert isinstance(widget, QtWidgets.QDoubleSpinBox)
                    widget.setValue(float(value or 0.0))
                elif kind == "choice":
                    assert isinstance(widget, QtWidgets.QComboBox)
                    index = widget.findText(str(value))
                    if index >= 0:
                        widget.setCurrentIndex(index)
                elif kind == "line":
                    assert isinstance(widget, QtWidgets.QLineEdit)
                    widget.setText("" if value is None else str(value))
                elif kind == "device":
                    assert isinstance(widget, QtWidgets.QComboBox)
                    index = widget.findData(str(value))
                    widget.setCurrentIndex(index if index >= 0 else 0)
                elif kind == "json":
                    assert isinstance(widget, QtWidgets.QPlainTextEdit)
                    widget.setPlainText(pretty_json(value))
        finally:
            self._suspend = False

    def extract_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {}
        for spec in self.schema:
            path = spec["path"]
            kind = spec["kind"]
            widget = self.widgets[path]
            if kind == "bool":
                assert isinstance(widget, QtWidgets.QCheckBox)
                value = widget.isChecked()
            elif kind == "int":
                assert isinstance(widget, QtWidgets.QSpinBox)
                value = widget.value()
            elif kind == "float":
                assert isinstance(widget, QtWidgets.QDoubleSpinBox)
                value = widget.value()
            elif kind == "choice":
                assert isinstance(widget, QtWidgets.QComboBox)
                value = widget.currentText()
            elif kind == "line":
                assert isinstance(widget, QtWidgets.QLineEdit)
                raw = widget.text().strip()
                value = None if spec.get("nullable") and raw == "" else raw
            elif kind == "device":
                assert isinstance(widget, QtWidgets.QComboBox)
                value = widget.currentData() or ""
            elif kind == "json":
                assert isinstance(widget, QtWidgets.QPlainTextEdit)
                value = parse_json_text(widget.toPlainText())
            else:
                raise ValueError(f"Unsupported kind {kind}")
            deep_set(config, path, value)
        return config

    def _emit_change(self, *args) -> None:
        if self._suspend:
            return
        try:
            cfg = self.extract_config()
        except Exception:
            return
        self.config_changed.emit(self.component_name, cfg)


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


class CVTriggerEditor(QtWidgets.QGroupBox):
    config_changed = QtCore.Signal(str, dict)

    def __init__(self, component_name: str, title: str, device_service: DeviceService, parent=None) -> None:
        super().__init__(title, parent)
        self.component_name = component_name
        self.device_service = device_service
        self._suspend = False
        self.rule_editors: list[CVRuleEditor] = []

        outer = QtWidgets.QVBoxLayout(self)

        self.runtime_status = QtWidgets.QLabel("Runtime status: idle")
        self.runtime_status.setWordWrap(True)
        self.runtime_status.setStyleSheet("color: #666;")
        outer.addWidget(self.runtime_status)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignTop)
        outer.addLayout(form)

        self.enabled = QtWidgets.QCheckBox()
        self.enabled.stateChanged.connect(self._emit_change)
        form.addRow("Enabled", self.enabled)

        self.model_path = QtWidgets.QLineEdit()
        self.model_path.editingFinished.connect(self._emit_change)
        form.addRow("Model path", self.model_path)

        self.shared_sens_note = QtWidgets.QLabel("Uses the shared game sensitivity from the top settings box.")
        self.shared_sens_note.setWordWrap(True)
        self.shared_sens_note.setStyleSheet("color: #666;")
        form.addRow("Sensitivity", self.shared_sens_note)

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
        form.addRow("Capture monitor", monitor_row)

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
        form.addRow("Game resolution", resolution_row)

        self.use_gsi_opponent_side = QtWidgets.QCheckBox()
        self.use_gsi_opponent_side.stateChanged.connect(self._update_target_side_visibility)
        self.use_gsi_opponent_side.stateChanged.connect(self._emit_change)
        form.addRow("Use GSI enemy side", self.use_gsi_opponent_side)

        self.manual_target_side = QtWidgets.QComboBox()
        self.manual_target_side.addItem("Terrorists", "terrorists")
        self.manual_target_side.addItem("Counter-Terrorists", "counter_terrorists")
        self.manual_target_side.addItem("Both", "both")
        self.manual_target_side.currentIndexChanged.connect(self._emit_change)
        form.addRow("Manual target side", self.manual_target_side)

        self.inference_confidence = QtWidgets.QDoubleSpinBox()
        self.inference_confidence.setRange(0.0, 1.0)
        self.inference_confidence.setDecimals(4)
        self.inference_confidence.setSingleStep(0.01)
        self.inference_confidence.valueChanged.connect(self._emit_change)
        form.addRow("Inference confidence", self.inference_confidence)

        self.inference_img_size = QtWidgets.QSpinBox()
        self.inference_img_size.setRange(32, 4096)
        self.inference_img_size.setSingleStep(32)
        self.inference_img_size.valueChanged.connect(self._emit_change)
        form.addRow("Inference image size", self.inference_img_size)

        self.jitter_deadzone_px = QtWidgets.QDoubleSpinBox()
        self.jitter_deadzone_px.setRange(0.0, 100.0)
        self.jitter_deadzone_px.setDecimals(2)
        self.jitter_deadzone_px.setSingleStep(0.25)
        self.jitter_deadzone_px.valueChanged.connect(self._emit_change)
        form.addRow("Jitter deadzone (px)", self.jitter_deadzone_px)

        self.near_smoothing_alpha = QtWidgets.QDoubleSpinBox()
        self.near_smoothing_alpha.setRange(0.01, 1.0)
        self.near_smoothing_alpha.setDecimals(3)
        self.near_smoothing_alpha.setSingleStep(0.05)
        self.near_smoothing_alpha.valueChanged.connect(self._emit_change)
        form.addRow("Near smoothing alpha", self.near_smoothing_alpha)

        self.near_smoothing_radius_px = QtWidgets.QDoubleSpinBox()
        self.near_smoothing_radius_px.setRange(1.0, 500.0)
        self.near_smoothing_radius_px.setDecimals(1)
        self.near_smoothing_radius_px.setSingleStep(1.0)
        self.near_smoothing_radius_px.valueChanged.connect(self._emit_change)
        form.addRow("Near smoothing radius (px)", self.near_smoothing_radius_px)

        self.x_prediction_enabled = QtWidgets.QCheckBox()
        self.x_prediction_enabled.stateChanged.connect(self._emit_change)
        form.addRow("Predict horizontal motion", self.x_prediction_enabled)

        self.x_prediction_lead_ms = QtWidgets.QDoubleSpinBox()
        self.x_prediction_lead_ms.setRange(0.0, 250.0)
        self.x_prediction_lead_ms.setDecimals(1)
        self.x_prediction_lead_ms.setSingleStep(1.0)
        self.x_prediction_lead_ms.valueChanged.connect(self._emit_change)
        form.addRow("Prediction lead (ms)", self.x_prediction_lead_ms)

        self.x_prediction_history_ms = QtWidgets.QDoubleSpinBox()
        self.x_prediction_history_ms.setRange(10.0, 500.0)
        self.x_prediction_history_ms.setDecimals(1)
        self.x_prediction_history_ms.setSingleStep(5.0)
        self.x_prediction_history_ms.valueChanged.connect(self._emit_change)
        form.addRow("Prediction history (ms)", self.x_prediction_history_ms)

        self.x_prediction_damping = QtWidgets.QDoubleSpinBox()
        self.x_prediction_damping.setRange(0.0, 1.0)
        self.x_prediction_damping.setDecimals(3)
        self.x_prediction_damping.setSingleStep(0.05)
        self.x_prediction_damping.valueChanged.connect(self._emit_change)
        form.addRow("Prediction damping", self.x_prediction_damping)

        self.x_prediction_max_delta_px = QtWidgets.QDoubleSpinBox()
        self.x_prediction_max_delta_px.setRange(0.0, 500.0)
        self.x_prediction_max_delta_px.setDecimals(1)
        self.x_prediction_max_delta_px.setSingleStep(1.0)
        self.x_prediction_max_delta_px.valueChanged.connect(self._emit_change)
        form.addRow("Max predicted X shift (px)", self.x_prediction_max_delta_px)

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
        form = self.layout().itemAt(1).layout() if self.layout().count() > 1 else None
        if isinstance(form, QtWidgets.QFormLayout):
            lbl = form.labelForField(self.manual_target_side)
            if lbl is not None:
                lbl.setVisible(manual_visible)

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
                        "SNAP_DISTANCE": 50,
                        "SETTLE_FRAMES": 2,
                        "CLICK_HOLD_MS": 15,
                        "COOLDOWN_MS": 250,
                        "SENS_COEFF": 1.2,
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
                "SNAP_DISTANCE": 50,
                "SETTLE_FRAMES": 2,
                "CLICK_HOLD_MS": 15,
                "COOLDOWN_MS": 250,
                "SENS_COEFF": 1.2,
                "CROSS_X_THRESH": 14,
                "CROSS_Y_THRESH_TOP": 18,
                "CROSS_Y_THRESH_BOT": 32,
            },
        )

    def _add_rule_editor(self, name: str, rule: dict[str, Any], emit_change: bool = True) -> None:
        editor = CVRuleEditor()
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

    def _emit_change(self, *args) -> None:
        if self._suspend:
            return
        try:
            cfg = self.extract_config()
        except Exception:
            return
        self.config_changed.emit(self.component_name, cfg)

class MainWindow(QtWidgets.QMainWindow):

    def __init__(self) -> None:
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

        top_panels = QtWidgets.QHBoxLayout()
        top_panels.addWidget(self._build_shared_settings_group(), 1)
        top_panels.addWidget(self._build_gsi_group(), 1)
        root.addLayout(top_panels)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        root.addWidget(self.scroll, 1)

        self.scroll_content = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QVBoxLayout(self.scroll_content)
        self.scroll.setWidget(self.scroll_content)

        self.component_editors: dict[str, Any] = {}
        for name, title, schema in component_schemas():
            box = CollapsibleBox(title)
            if name == "cv_trigger":
                editor = CVTriggerEditor(name, title, device_service=self.device_service)
            else:
                editor = ComponentEditor(name, title, schema, device_service=self.device_service)
            editor.config_changed.connect(self._on_component_config_changed)
            box.content_layout.addWidget(editor)
            self.component_editors[name] = editor
            self.scroll_layout.addWidget(box)

        self.scroll_layout.addStretch(1)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setFixedHeight(220)
        root.addWidget(self.log)

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

        self.save_profile_btn = QtWidgets.QPushButton("Save Profile")
        self.save_profile_btn.clicked.connect(self.save_current_profile)
        layout.addWidget(self.save_profile_btn)

        self.apply_profile_btn = QtWidgets.QPushButton("Apply Profile")
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

    def _build_shared_settings_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Shared Input / Sensitivity")
        layout = QtWidgets.QFormLayout(group)

        self.shared_keyboard_device = QtWidgets.QComboBox()
        self.shared_keyboard_device.currentTextChanged.connect(self._on_shared_settings_changed)
        layout.addRow("Keyboard device", self.shared_keyboard_device)

        self.shared_game_sensitivity = QtWidgets.QDoubleSpinBox()
        self.shared_game_sensitivity.setRange(0.01, 50.0)
        self.shared_game_sensitivity.setDecimals(4)
        self.shared_game_sensitivity.setSingleStep(0.01)
        self.shared_game_sensitivity.valueChanged.connect(self._on_shared_settings_changed)
        layout.addRow("Game / program sensitivity", self.shared_game_sensitivity)

        note = QtWidgets.QLabel(
            "Used by keyboard-based features for the selected input device, and by recoil / CV trigger for sensitivity scaling."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        layout.addRow("", note)
        return group

    def _build_gsi_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Game State Integration")
        layout = QtWidgets.QFormLayout(group)

        self.gsi_enabled = QtWidgets.QCheckBox()
        self.gsi_enabled.stateChanged.connect(self._on_gsi_changed)
        layout.addRow("Enabled", self.gsi_enabled)

        self.gsi_host = QtWidgets.QLineEdit()
        self.gsi_host.editingFinished.connect(self._on_gsi_changed)
        layout.addRow("Host", self.gsi_host)

        self.gsi_port = QtWidgets.QSpinBox()
        self.gsi_port.setRange(1, 65535)
        self.gsi_port.valueChanged.connect(self._on_gsi_changed)
        layout.addRow("Port", self.gsi_port)

        self.gsi_last_state = QtWidgets.QLabel("No data yet.")
        layout.addRow("Last state", self.gsi_last_state)

        return group


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

        screen_offset_x = (mouse_x / base_sens_mult_x) * float(settings["screen_scale"])
        screen_offset_y = (mouse_y / base_sens_mult_y) * float(settings["screen_scale"])

        bullet_x = left + mon_width / 2.0 - screen_offset_x
        bullet_y = top + mon_height / 2.0 - screen_offset_y
        self.bullet_overlay.show_point(bullet_x, bullet_y)

    def _runtime_status(self, source: str, message: str) -> None:
        if self._closing or not hasattr(self, "current_profile_data"):
            return
        try:
            self.log_bridge.message.emit(source, message)
        except RuntimeError:
            return

    def _append_log(self, source: str, message: str) -> None:
        self.log.appendPlainText(f"{source}: {message}")
        editor = self.component_editors.get(source)
        if editor is not None:
            editor.set_runtime_status(message.replace("[INFO] ", "").replace("[WARNING] ", "").replace("[ERROR] ", ""))
        if source == "gsi" and "weapon=" in message:
            self.gsi_last_state.setText(message.replace("[INFO] ", ""))

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
        devices = self.device_service.list_keyboards()
        current = self.shared_keyboard_device.currentData() if hasattr(self, "shared_keyboard_device") else ""
        if hasattr(self, "shared_keyboard_device"):
            self.shared_keyboard_device.blockSignals(True)
            self.shared_keyboard_device.clear()
            self.shared_keyboard_device.addItem("Auto-detect", "")
            for item in devices:
                self.shared_keyboard_device.addItem(item.label, item.path)
            index = self.shared_keyboard_device.findData(current)
            if index >= 0:
                self.shared_keyboard_device.setCurrentIndex(index)
            self.shared_keyboard_device.blockSignals(False)
        for editor in self.component_editors.values():
            editor.refresh_devices()

    def load_profile(self, name: str) -> None:
        self._loading_profile = True
        try:
            self.current_profile_name = name
            self.current_profile_data = self.profile_store.load_profile(name)

            gsi = deep_get(self.current_profile_data, "app.gsi", {})
            self.gsi_enabled.setChecked(bool(gsi.get("enabled", True)))
            self.gsi_host.setText(str(gsi.get("host", "127.0.0.1")))
            self.gsi_port.setValue(int(gsi.get("port", 3000)))

            shared = deep_get(self.current_profile_data, "app.shared", {})
            index = self.shared_keyboard_device.findData(str(shared.get("keyboard_device_path", "")))
            self.shared_keyboard_device.setCurrentIndex(index if index >= 0 else 0)
            self.shared_game_sensitivity.setValue(float(shared.get("game_sensitivity", 1.0) or 1.0))

            for component_name, editor in self.component_editors.items():
                editor.load_config(deep_get(self.current_profile_data, f"components.{component_name}", {}))
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
        deep_set(self.current_profile_data, "app.gsi.enabled", self.gsi_enabled.isChecked())
        deep_set(self.current_profile_data, "app.gsi.host", self.gsi_host.text().strip() or "127.0.0.1")
        deep_set(self.current_profile_data, "app.gsi.port", self.gsi_port.value())
        deep_set(self.current_profile_data, "app.shared.keyboard_device_path", self.shared_keyboard_device.currentData() or "")
        deep_set(self.current_profile_data, "app.shared.game_sensitivity", self.shared_game_sensitivity.value())

        for name, editor in self.component_editors.items():
            extracted = editor.extract_config()
            if name == "cv_trigger":
                cfg = deep_copy(extracted if isinstance(extracted, dict) else {})
            else:
                existing = deep_get(self.current_profile_data, f"components.{name}", {})
                cfg = _deep_merge_preserving_hidden(existing if isinstance(existing, dict) else {}, extracted)
            deep_set(self.current_profile_data, f"components.{name}", cfg)

    def _on_component_config_changed(self, component_name: str, config: dict) -> None:
        if self._loading_profile:
            return
        if component_name == "cv_trigger":
            merged = deep_copy(config if isinstance(config, dict) else {})
        else:
            existing = deep_get(self.current_profile_data, f"components.{component_name}", {})
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

    def closeEvent(self, event) -> None:
        self._closing = True
        self.bullet_overlay.hide_overlay()
        for component in self.runtime.components.values():
            component.set_status_callback(lambda *_args, **_kwargs: None)
        self.runtime.stop_all()
        super().closeEvent(event)


def component_schemas() -> list[tuple[str, str, list[dict[str, Any]]]]:
    return [
        (
            "bhop",
            "Bhop",
            [
                {"path": "enabled", "label": "Enabled", "kind": "bool"},
                                {"path": "tap_interval_ms", "label": "Tap interval (ms)", "kind": "int", "min": 1, "max": 500},
            ],
        ),
        (
            "snap_tap",
            "Snap Tap / Null Binds",
            [
                {"path": "enabled", "label": "Enabled", "kind": "bool"},
                            ],
        ),
        (
            "counter_strafe",
            "Counter Strafe",
            [
                {"path": "enabled", "label": "Enabled", "kind": "bool"},
                                {"path": "base_counter_ms", "label": "Base counter ms", "kind": "int", "min": 0, "max": 1000},
                {"path": "full_speed_ms", "label": "Full speed ms", "kind": "int", "min": 1, "max": 1000},
                {"path": "min_counter_ms", "label": "Min counter ms", "kind": "int", "min": 0, "max": 1000},
                {"path": "max_counter_ms", "label": "Max counter ms", "kind": "int", "min": 1, "max": 1000},
                {"path": "shift_factor", "label": "Shift factor", "kind": "float", "min": 0.0, "max": 5.0, "step": 0.01},
                {"path": "ctrl_factor", "label": "Ctrl factor", "kind": "float", "min": 0.0, "max": 5.0, "step": 0.01},
                {"path": "curve", "label": "Curve", "kind": "choice", "choices": ["linear", "exp"]},
                {"path": "manual_brake_window_ms", "label": "Manual brake window ms", "kind": "int", "min": 0, "max": 1000},
                {"path": "manual_brake_max_ms", "label": "Manual brake max ms", "kind": "int", "min": 0, "max": 1000},
            ],
        ),
        (
            "recoil",
            "Recoil Control",
            [
                {"path": "enabled", "label": "Enabled", "kind": "bool"},
                {"path": "axis_strength_percent.x", "label": "X strength %", "kind": "float", "min": 0.0, "max": 300.0, "step": 1.0},
                {"path": "axis_strength_percent.y", "label": "Y strength %", "kind": "float", "min": 0.0, "max": 300.0, "step": 1.0},
                {"path": "movement.frequency_hz", "label": "Update frequency (Hz)", "kind": "int", "min": 30, "max": 1000},
                {"path": "movement.max_delta_per_event", "label": "Max delta per event (px)", "kind": "int", "min": 0, "max": 50},
                {"path": "noise.strength_px", "label": "Noise amount (px)", "kind": "float", "min": 0.0, "max": 5.0, "step": 0.01, "decimals": 3},
                {"path": "return_mouse.enabled", "label": "Return mouse after spray", "kind": "bool"},
                {"path": "return_mouse.delay_ms", "label": "Return delay (ms)", "kind": "int", "min": 0, "max": 500},
                {"path": "return_mouse.duration_ms", "label": "Return duration (ms)", "kind": "int", "min": 20, "max": 1000},
                {"path": "return_mouse.y_percent", "label": "Return Y %", "kind": "float", "min": 0.0, "max": 100.0, "step": 1.0, "decimals": 1, "default": 100.0},
                {"path": "overlay.enabled", "label": "Show bullet overlay", "kind": "bool"},
                {"path": "overlay.screen_scale", "label": "Spray / overlay scale", "kind": "float", "min": 0.01, "max": 2.0, "step": 0.01, "decimals": 3},
                {"path": "overlay.diameter_px", "label": "Overlay size (px)", "kind": "int", "min": 4, "max": 64},
                {"path": "overlay.opacity", "label": "Overlay opacity", "kind": "float", "min": 0.05, "max": 1.0, "step": 0.05, "decimals": 2},
            ],
        ),
        (
            "pixel_trigger",
            "Pixel Trigger",
            [
                {"path": "enabled", "label": "Enabled", "kind": "bool"},
                {"path": "hold_key_name", "label": "Hold key", "kind": "line"},
                {"path": "threshold", "label": "Threshold", "kind": "float", "min": 0.0, "max": 500.0, "step": 0.1},
                {"path": "click_delay", "label": "Click delay (s)", "kind": "float", "min": 0.0, "max": 5.0, "step": 0.001, "decimals": 4},
                {"path": "cooldown", "label": "Cooldown (s)", "kind": "float", "min": 0.0, "max": 5.0, "step": 0.001, "decimals": 4},
                {"path": "poll_interval", "label": "Poll interval (s)", "kind": "float", "min": 0.0001, "max": 1.0, "step": 0.0005, "decimals": 4},
                {"path": "monitor_index", "label": "Monitor index", "kind": "int", "min": 1, "max": 16},
                {"path": "x", "label": "Fixed X", "kind": "line", "nullable": True},
                {"path": "y", "label": "Fixed Y", "kind": "line", "nullable": True},
            ],
        ),
        (
            "cv_trigger",
            "CV Trigger / Aim Assist",
            [],
        ),
    ]
