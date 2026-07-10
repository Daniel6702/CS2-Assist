from __future__ import annotations

__all__ = ["MainWindow", "apply_style", "component_schemas"]


def __getattr__(name: str):
    if name == "component_schemas":
        from .schemas import component_schemas

        return component_schemas
    if name == "apply_style":
        from .styles import apply_style

        return apply_style
    if name == "MainWindow":
        from .main_window import MainWindow

        return MainWindow
    raise AttributeError(f"module 'app.ui' has no attribute '{name}'")
