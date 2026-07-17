from __future__ import annotations

from pathlib import Path
from typing import Any

from app.components.cv_trigger.curve_config import build_curve_library

APP_ROOT = Path(__file__).resolve().parents[1]
RESOURCES_DIR = APP_ROOT / "resources"
PROFILES_DIR = APP_ROOT / "profiles"
MODEL_FILE = RESOURCES_DIR / "best.pt"


def default_profile() -> dict[str, Any]:
    return {
        "name": "Default",
        "app": {
            "gsi": {
                "enabled": True,
                "host": "127.0.0.1",
                "port": 3000,
            },
            "shared": {
                "keyboard_device_path": "",
                "game_sensitivity": 1.0,
                "game_resolution": {"width": 1600, "height": 1200},
            },
            "hotkeys": {
                "cv_trigger": "F1",
                "recoil": "F2",
                "pixel_trigger": "F3",
                "movement": "F4",
                "stop_all": "F5",
                "overlay": "Insert",
            },
            "safety": {
                "enabled": False,
                "obscure_device_names": False,
                "recoil": {
                    "jitter_step_fraction": 0.0,
                    "jitter_noise_mix_fraction": 0.0,
                    "jitter_noise_decay_fraction": 0.0,
                },
                "pixel_trigger": {
                    "jitter_cooldown_fraction": 0.0,
                    "jitter_click_delay_fraction": 0.0,
                    "jitter_poll_fraction": 0.0,
                },
                "cv_trigger": {
                    "jitter_prediction_fraction": 0.0,
                    "jitter_sleep_fraction": 0.0,
                    "jitter_click_hold_fraction": 0.0,
                    "jitter_cooldown_fraction": 0.0,
                    "eased_movement_enabled": False,
                },
            },
        },
        "components": {
            "bhop": {
                "enabled": False,
                "tap_interval_ms": 20,
            },
            "snap_tap": {
                "enabled": False,
            },
            "counter_strafe": {
                "enabled": False,
                "base_counter_ms": 100,
                "full_speed_ms": 180,
                "min_counter_ms": 8,
                "max_counter_ms": 120,
                "shift_factor": 0.45,
                "ctrl_factor": 0.35,
                "curve": "linear",
                "manual_brake_window_ms": 150,
                "manual_brake_max_ms": 170,
            },
            "recoil": {
                "enabled": False,
                "axis_strength_percent": {"x": 100.0, "y": 100.0},
                "sensitivity": {
                    "enabled": True,
                    "reference_sens": 2.52,
                    "program_sens": 2.52,
                    "apply_to_axis": {"x": True, "y": True},
                },
                "movement": {
                    "frequency_hz": 165,
                    "max_delta_per_event": 3,
                },
                "noise": {
                    "strength_px": 0.0,
                },
                "return_mouse": {
                    "enabled": False,
                    "delay_ms": 20,
                    "duration_ms": 140,
                    "y_percent": 100.0,
                },
                "overlay": {
                    "enabled": False,
                    "screen_scale": 0.30,
                    "diameter_px": 12,
                    "opacity": 0.90,
                },
            },
            "pixel_trigger": {
                "enabled": False,
                "hold_key_name": "shift",
                "threshold": 35.0,
                "click_delay": 0.05,
                "cooldown": 0.15,
                "poll_interval": 0.001,
                "monitor_index": 1,
                "x": None,
                "y": None,
            },
            "cv_trigger": {
                "enabled": False,
                "model_path": str(MODEL_FILE),
                "anti_oscillation_radius_px": 24.0,
                "anti_oscillation_reserve_counts": 1,
                "anti_oscillation_lock_frames": 2,
                "aim_curves": build_curve_library(),
                "configs": {
                    "rifle_alt_aim_only": {
                        "enabled": True,
                        "priority": 0,
                        "activation": {"device": "keyboard", "key": "alt"},
                        "allowed_weapons": [
                            "weapon_ak47",
                            "weapon_m4a1",
                            "weapon_m4a1_silencer",
                            "weapon_famas",
                            "weapon_galilar",
                            "weapon_aug",
                            "weapon_sg556",
                        ],
                        "auto_shoot": False,
                        "auto_shoot_aim_cooldown_ms": 0,
                        "AIM_MODE": "head",
                        "HEAD_OFFSET": 0.10,
                        "SNAP_DISTANCE": 200,
                        "SETTLE_FRAMES": 2,
                        "CLICK_HOLD_MS": 20,
                        "COOLDOWN_MS": 350,
                        "AIM_STRENGTH": 0.5,
                        "AIM_CURVE_ID": "linear",
                        "MAX_AIM_SPEED_PX": 50,
                        "SMOOTHING_ALPHA": 0.0,
                        "NOISE_AMOUNT": 0.0,
                        "BODY_KNEE_OFFSET": 0.50,
                        "AUTO_SHOOT_ZONE_WIDTH": 60,
                        "AUTO_SHOOT_ZONE_HEIGHT": 40,
                        "AUTO_SHOOT_ZONE_Y_POS": 0.30,
                    },
                    "sniper_always_autoshoot": {
                        "enabled": True,
                        "priority": 0,
                        "activation": {"mode": "always"},
                        "allowed_weapons": ["weapon_awp", "weapon_ssg08", "weapon_scar20", "weapon_g3sg1"],
                        "auto_shoot": True,
                        "auto_shoot_aim_cooldown_ms": 0,
                        "AIM_MODE": "body",
                        "HEAD_OFFSET": 0.08,
                        "SNAP_DISTANCE": 500,
                        "SETTLE_FRAMES": 1,
                        "CLICK_HOLD_MS": 25,
                        "COOLDOWN_MS": 500,
                        "AIM_STRENGTH": 0.2,
                        "AIM_CURVE_ID": "linear",
                        "MAX_AIM_SPEED_PX": 30,
                        "SMOOTHING_ALPHA": 0.0,
                        "NOISE_AMOUNT": 0.0,
                        "BODY_KNEE_OFFSET": 0.50,
                        "AUTO_SHOOT_ZONE_WIDTH": 40,
                        "AUTO_SHOOT_ZONE_HEIGHT": 85,
                        "AUTO_SHOOT_ZONE_Y_POS": 0.50,
                    },
                },
            },
        },
    }
