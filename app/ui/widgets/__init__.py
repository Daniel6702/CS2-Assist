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
    raise AttributeError(f"module 'app.ui.widgets' has no attribute '{name}'")
