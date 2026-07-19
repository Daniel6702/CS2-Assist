from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from app.common import deep_get, deep_set, parse_json_text, pretty_json
from app.device_service import DeviceService


class ColorButton(QtWidgets.QPushButton):
    color_changed = QtCore.Signal(QtGui.QColor)

    def __init__(self, color: QtGui.QColor = QtGui.QColor(255, 0, 0), parent=None) -> None:
        super().__init__(parent)
        self._color = color
        self.setFixedSize(28, 20)
        self.clicked.connect(self._pick_color)
        self._update_style()

    def _update_style(self) -> None:
        self.setStyleSheet(f"background-color: {self._color.name()}; border: 1px solid #555; border-radius: 3px;")

    def _pick_color(self) -> None:
        dialog = QtWidgets.QColorDialog(self._color, self)
        dialog.setOption(QtWidgets.QColorDialog.ShowAlphaChannel, True)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self._color = dialog.selectedColor()
            self._update_style()
            self.color_changed.emit(self._color)

    def color(self) -> QtGui.QColor:
        return self._color

    def set_color(self, color: QtGui.QColor) -> None:
        self._color = color
        self._update_style()


class ComponentEditor(QtWidgets.QGroupBox):
    config_changed = QtCore.Signal(str, dict)

    def __init__(self, component_name: str, title: str, schema: list[dict[str, Any]], device_service: DeviceService, parent=None) -> None:
        super().__init__(title, parent)
        self.component_name = component_name
        self.schema = schema
        self.device_service = device_service
        self.widgets: dict[str, QtWidgets.QWidget] = {}
        self._advanced_container: QtWidgets.QWidget | None = None
        self._advanced_btn: QtWidgets.QPushButton | None = None
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
        form.setVerticalSpacing(12)
        outer.addLayout(form)

        advanced_form: QtWidgets.QFormLayout | None = None

        for spec in schema:
            label = spec["label"]
            path = spec["path"]
            widget = self._create_widget(spec)
            self.widgets[path] = widget

            if spec.get("advanced"):
                if advanced_form is None:
                    advanced_btn = QtWidgets.QPushButton("Advanced >>")
                    advanced_btn.setCheckable(True)
                    advanced_btn.setChecked(False)
                    advanced_btn.toggled.connect(self._on_advanced_toggled)
                    self._advanced_btn = advanced_btn

                    container = QtWidgets.QWidget()
                    container.setVisible(False)
                    self._advanced_container = container
                    advanced_form = QtWidgets.QFormLayout(container)
                    advanced_form.setLabelAlignment(QtCore.Qt.AlignTop)
                    advanced_form.setHorizontalSpacing(12)
                    advanced_form.setVerticalSpacing(12)

                    form.addRow(advanced_btn, container)

                advanced_form.addRow(label, widget)
            else:
                form.addRow(label, widget)

    def set_runtime_status(self, message: str) -> None:
        self.runtime_status.setText(f"Runtime status: {message}")

    def _on_advanced_toggled(self, checked: bool) -> None:
        if self._advanced_container is not None:
            self._advanced_container.setVisible(checked)
        if self._advanced_btn is not None:
            self._advanced_btn.setText("Advanced <<" if checked else "Advanced >>")

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
        if kind == "color":
            widget = ColorButton()
            widget.color_changed.connect(self._emit_change)
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
                elif kind == "color":
                    assert isinstance(widget, ColorButton)
                    if isinstance(value, str):
                        widget.set_color(QtGui.QColor(value))
                    elif isinstance(value, (list, tuple)) and len(value) >= 3:
                        widget.set_color(QtGui.QColor(*value[:3]))
                    else:
                        widget.set_color(QtGui.QColor(255, 0, 0))
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
            elif kind == "color":
                assert isinstance(widget, ColorButton)
                c = widget.color()
                value = [c.red(), c.green(), c.blue(), c.alpha()]
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
