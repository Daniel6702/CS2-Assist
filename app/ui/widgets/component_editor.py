from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from app.common import deep_get, deep_set, parse_json_text, pretty_json
from app.device_service import DeviceService


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
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        self.runtime_status = QtWidgets.QLabel("Runtime: idle")
        self.runtime_status.setStyleSheet("color: #888; font-size: 11px;")
        self.runtime_status.setFixedHeight(18)
        outer.addWidget(self.runtime_status)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
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
