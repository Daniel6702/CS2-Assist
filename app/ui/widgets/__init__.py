from __future__ import annotations

__all__ = [
    "LogBridge",
    "BulletImpactOverlay",
    "CollapsibleBox",
    "ComponentEditor",
    "ColorButton",
    "CVRuleEditor",
    "CVTriggerEditor",
    "AimCurveEditor",
    "CS2CrosshairCodec",
    "CrosshairRenderer",
    "PixelGridWidget",
]


def __getattr__(name: str):
    if name == "LogBridge":
        from .log_bridge import LogBridge

        return LogBridge
    if name == "BulletImpactOverlay":
        from .bullet_overlay import BulletImpactOverlay

        return BulletImpactOverlay
    if name == "CollapsibleBox":
        from .collapsible_box import CollapsibleBox

        return CollapsibleBox
    if name in {"ComponentEditor", "ColorButton"}:
        from .component_editor import ColorButton, ComponentEditor

        return {"ComponentEditor": ComponentEditor, "ColorButton": ColorButton}[name]
    if name == "CVRuleEditor":
        from .cv_rule_editor import CVRuleEditor

        return CVRuleEditor
    if name == "CVTriggerEditor":
        from .cv_trigger_editor import CVTriggerEditor

        return CVTriggerEditor
    if name == "AimCurveEditor":
        from .curve_editor import AimCurveEditor

        return AimCurveEditor
    if name == "CS2CrosshairCodec":
        from .crosshair_codec import CS2CrosshairCodec

        return CS2CrosshairCodec
    if name == "CrosshairRenderer":
        from .crosshair_renderer import CrosshairRenderer

        return CrosshairRenderer
    if name == "PixelGridWidget":
        from .crosshair_grid_widget import PixelGridWidget

        return PixelGridWidget
    raise AttributeError(f"module 'app.ui.widgets' has no attribute '{name}'")
