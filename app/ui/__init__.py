from __future__ import annotations

# Lazy imports - only import on demand to avoid triggering heavy dependencies
# from .main_window import MainWindow
from .schemas import component_schemas
from .styles import apply_style

__all__ = ['component_schemas']
__all__ += ["apply_style"]
# __all__ += ["MainWindow"]

def __getattr__(name: str):
    if name == "MainWindow":
        from .main_window import MainWindow
        return MainWindow
    raise AttributeError(f"module 'app.ui' has no attribute '{name}'")
