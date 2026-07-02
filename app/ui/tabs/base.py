from __future__ import annotations

import ast
from abc import abstractmethod
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtWidgets

from app.common import deep_get, deep_set, parse_json_text, pretty_json
from app.device_service import DeviceService


class BaseTab(QtWidgets.QWidget):
    @abstractmethod
    def load_config(self, config: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def extract_config(self) -> dict[str, Any]:
        raise NotImplementedError


def load_widget_class(name: str) -> type:
    try:
        from app.ui import widgets

        widget_class = getattr(widgets, name, None)
        if widget_class is not None:
            return widget_class
    except ImportError:
        pass

    return _load_legacy_widget_classes()[name]


def _load_legacy_widget_classes() -> dict[str, type]:
    legacy_ui_path = Path(__file__).resolve().parents[2] / "ui.py"
    tree = ast.parse(legacy_ui_path.read_text(encoding="utf-8"), filename=str(legacy_ui_path))
    selected_names = {
        "_infer_target_type_from_rule_ui",
        "_normalize_cv_trigger_config_for_ui",
        "CVRuleEditor",
        "ComponentEditor",
        "CVTriggerEditor",
    }
    selected_nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.ClassDef) and node.name in selected_names
    ]
    module = ast.Module(body=selected_nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, Any] = {
        "Any": Any,
        "DeviceService": DeviceService,
        "QtCore": QtCore,
        "QtWidgets": QtWidgets,
        "deep_get": deep_get,
        "deep_set": deep_set,
        "parse_json_text": parse_json_text,
        "pretty_json": pretty_json,
    }
    exec(compile(module, str(legacy_ui_path), "exec"), namespace)
    return {
        "ComponentEditor": namespace["ComponentEditor"],
        "CVTriggerEditor": namespace["CVTriggerEditor"],
    }
