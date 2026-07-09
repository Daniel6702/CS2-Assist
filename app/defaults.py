from __future__ import annotations

from pathlib import Path
from typing import Any

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
                "monitor": {"top": 0, "left": 0, "width": 2560, "height": 1440},
                "game_resolution": {"width": 1600, "height": 1200},
                "configs": {
                    "rifle_alt_aim_only": {
                        "enabled": True,
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
                        "AIM_STRENGTH": 50.0,
                        "RESPONSE_CURVE": "proportional",
                        "CURVE_INTENSITY": 1.0,
                        "CONSTANT_SPEED_PX": 50,
                        "ACCEL_BOOST": 1.0,
                        "ANTI_OVERSHOOT": True,
                        "SMOOTHING_ALPHA": 0.0,
                        "NOISE_AMOUNT": 0.0,
                        "BODY_KNEE_OFFSET": 0.50,
                        "CROSS_X_THRESH": 30,
                        "CROSS_Y_THRESH_TOP": 20,
                        "CROSS_Y_THRESH_BOT": 35,
                    },
                    "sniper_always_autoshoot": {
                        "enabled": True,
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
                        "AIM_STRENGTH": 20.0,
                        "RESPONSE_CURVE": "proportional",
                        "CURVE_INTENSITY": 1.5,
                        "CONSTANT_SPEED_PX": 30,
                        "ACCEL_BOOST": 1.0,
                        "ANTI_OVERSHOOT": True,
                        "SMOOTHING_ALPHA": 0.0,
                        "NOISE_AMOUNT": 0.0,
                        "BODY_KNEE_OFFSET": 0.50,
                        "CROSS_X_THRESH": 20,
                        "CROSS_Y_THRESH_TOP": 15,
                        "CROSS_Y_THRESH_BOT": 70,
                    },
                },
            },
        },
    }
