from typing import Any, Dict, List, Tuple

_SchemaList = List[Tuple[str, str, List[Dict[str, Any]]]]


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
                {"path": "base_counter_ms", "label": "Base counter ms", "kind": "int", "min": 0, "max": 1000, "advanced": True},
                {"path": "full_speed_ms", "label": "Full speed ms", "kind": "int", "min": 1, "max": 1000, "advanced": True},
                {"path": "min_counter_ms", "label": "Min counter ms", "kind": "int", "min": 0, "max": 1000, "advanced": True},
                {"path": "max_counter_ms", "label": "Max counter ms", "kind": "int", "min": 1, "max": 1000, "advanced": True},
                {"path": "shift_factor", "label": "Shift factor", "kind": "float", "min": 0.0, "max": 5.0, "step": 0.01, "advanced": True},
                {"path": "ctrl_factor", "label": "Ctrl factor", "kind": "float", "min": 0.0, "max": 5.0, "step": 0.01, "advanced": True},
                {"path": "curve", "label": "Curve", "kind": "choice", "choices": ["linear", "exp"], "advanced": True},
                {"path": "manual_brake_window_ms", "label": "Manual brake window ms", "kind": "int", "min": 0, "max": 1000, "advanced": True},
                {"path": "manual_brake_max_ms", "label": "Manual brake max ms", "kind": "int", "min": 0, "max": 1000, "advanced": True},
            ],
        ),
        (
            "jump_throw",
            "Jump Throw",
            [
                {"path": "enabled", "label": "Enabled", "kind": "bool"},
                {"path": "key_name", "label": "Key", "kind": "line", "default": "v"},
            ],
        ),
        (
            "auto_air_strafe",
            "Auto Air Strafe",
            [
                {"path": "enabled", "label": "Enabled", "kind": "bool"},
                {"path": "key_name", "label": "Activation / jump key", "kind": "line", "default": "space"},
                {"path": "strafe_count", "label": "Number of strafes", "kind": "int", "min": 1, "max": 100, "default": 8},
                {"path": "jump_duration_ms", "label": "Jump duration ms", "kind": "int", "min": 100, "max": 2000, "default": 800, "advanced": True},
                {"path": "start_delay_ms", "label": "Strafe start delay ms", "kind": "int", "min": 0, "max": 1000, "default": 0, "advanced": True},
            ],
        ),
        (
            "recoil",
            "Recoil Control",
            [
                {"path": "enabled", "label": "Enabled", "kind": "bool"},
                {"path": "axis_strength_percent.x", "label": "X strength %", "kind": "float", "min": 0.0, "max": 300.0, "step": 1.0},
                {"path": "axis_strength_percent.y", "label": "Y strength %", "kind": "float", "min": 0.0, "max": 300.0, "step": 1.0},
                {"path": "noise.strength_px", "label": "Noise amount (px)", "kind": "float", "min": 0.0, "max": 5.0, "step": 0.01, "decimals": 3},
                {"path": "return_mouse.enabled", "label": "Return mouse after spray", "kind": "bool"},
                {"path": "return_mouse.delay_ms", "label": "Return delay (ms)", "kind": "int", "min": 0, "max": 500},
                {"path": "return_mouse.duration_ms", "label": "Return duration (ms)", "kind": "int", "min": 20, "max": 1000},
                {"path": "return_mouse.y_percent", "label": "Return Y %", "kind": "float", "min": 0.0, "max": 100.0, "step": 1.0, "decimals": 1, "default": 100.0},
                {"path": "overlay.enabled", "label": "Show bullet overlay", "kind": "bool"},
                {"path": "overlay.screen_scale", "label": "Spray / overlay scale", "kind": "float", "min": 0.01, "max": 2.0, "step": 0.01, "decimals": 3},
                {"path": "overlay.diameter_px", "label": "Overlay size (px)", "kind": "int", "min": 4, "max": 64},
                {"path": "overlay.opacity", "label": "Overlay opacity", "kind": "float", "min": 0.05, "max": 1.0, "step": 0.05, "decimals": 2},
                {"path": "overlay.color", "label": "Overlay color", "kind": "color"},
            ],
        ),
        (
            "pixel_trigger",
            "Pixel Trigger",
            [
                {"path": "enabled", "label": "Enabled", "kind": "bool"},
                {"path": "hold_key_name", "label": "Hold key", "kind": "line"},
                {"path": "crosshair_code", "label": "Crosshair Code", "kind": "line", "advanced": True},
                {"path": "monitor_pixel_x", "label": "Monitor pixel X", "kind": "line", "nullable": True, "advanced": True},
                {"path": "monitor_pixel_y", "label": "Monitor pixel Y", "kind": "line", "nullable": True, "advanced": True},
                {"path": "scope_width", "label": "Scope width", "kind": "int", "min": 1, "max": 6, "default": 1, "advanced": True},
                {"path": "scope_monitor_pixel_x", "label": "Scope monitor pixel X", "kind": "line", "nullable": True, "advanced": True},
                {"path": "scope_monitor_pixel_y", "label": "Scope monitor pixel Y", "kind": "line", "nullable": True, "advanced": True},
                {"path": "threshold", "label": "Threshold", "kind": "float", "min": 0.0, "max": 500.0, "step": 0.1, "advanced": True},
                {"path": "click_delay", "label": "Click delay (s)", "kind": "float", "min": 0.0, "max": 5.0, "step": 0.001, "decimals": 4, "advanced": True},
                {"path": "cooldown", "label": "Cooldown (s)", "kind": "float", "min": 0.0, "max": 5.0, "step": 0.001, "decimals": 4, "advanced": True},
                {"path": "poll_interval", "label": "Poll interval (s)", "kind": "float", "min": 0.0001, "max": 1.0, "step": 0.0005, "decimals": 4, "advanced": True},
                {"path": "monitor_index", "label": "Monitor index", "kind": "int", "min": 1, "max": 16, "advanced": True},
                {"path": "x", "label": "Fixed X (fallback)", "kind": "line", "nullable": True, "advanced": True},
                {"path": "y", "label": "Fixed Y (fallback)", "kind": "line", "nullable": True, "advanced": True},
            ],
        ),
        (
            "cv_trigger",
            "CV Aim Assist",
            [],
        ),
    ]
