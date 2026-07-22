# CS2 Assist

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-not%20specified-lightgrey)
![Platform](https://img.shields.io/badge/platform-linux-lightgrey)

CS2 Assist is a Python/PySide6 desktop application for configuring and running Counter-Strike 2 assistance components from JSON profiles. The application starts a Qt GUI, stores settings in `profiles/*.json`, optionally listens for CS2 Game State Integration (GSI) data, and coordinates runtime components through a shared manager.

## Table Of Contents

- [Overview](#overview)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Overview

CS2 Assist provides a GUI for profile-based configuration of these runtime components:

- Bhop
- Snap Tap / Null Binds
- Counter Strafe
- Long Jump
- Recoil Control
- Pixel Trigger
- CV Trigger / Aim Assist

The GUI entrypoint is `app/main.py`. It creates a `QApplication`, applies the application style, opens `MainWindow`, and starts the Qt event loop. `MainWindow` loads the selected profile, renders tabs for shared settings, GSI, and each component, saves profile edits, and applies runtime changes.

## Requirements

- Python 3.10+
- Linux for keyboard filtering and virtual input support
- Counter-Strike 2
- CS2 Game State Integration (GSI) if GSI gating or weapon-aware behavior is enabled
- Write access to CS2's `game/csgo/cfg` folder for first-run setup
- Permission to read Linux input event devices such as `/dev/input/event*`
- Permission to create virtual input devices through `uinput`

Python dependencies are listed in `requirements.txt`:

- `PySide6` for the desktop UI
- `evdev` and `python-uinput` for Linux input capture and virtual devices
- `mss`, `numpy`, `opencv-python`, `torch`, and `ultralytics` for screen capture and CV trigger inference
- `pynput` and `pyautogui` for keyboard/mouse interaction paths

## Installation

Install Python dependencies from the project root:

```bash
pip install -r requirements.txt
```

Load the Linux `uinput` module before running components that create virtual input devices:

```bash
sudo modprobe uinput
```

If `uinput` is not available after reboot, configure your system to load it at boot. The exact location is distribution-specific, but a common setup is:

```bash
echo uinput | sudo tee /etc/modules-load.d/uinput.conf
```

Grant your user access to input devices and `uinput`. One common udev rule is:

```udev
KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
KERNEL=="event*", SUBSYSTEM=="input", GROUP="input", MODE="0660"
```

For example, place those rules in `/etc/udev/rules.d/99-cs2-assist-input.rules`, reload udev, and add your user to the `input` group:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
sudo usermod -aG input "$USER"
```

Log out and back in after changing group membership.

Configure CS2 GSI to send JSON POST requests to the host and port shown in the GSI tab. The default profile uses:

```text
http://127.0.0.1:3000
```

## Usage

Run the application from the project root:

```bash
python app/main.py
```

On first run, CS2 Assist opens a setup window asking for the CS2 game root folder. Select the root folder that contains `game/csgo/cfg`; the app validates that cfg folder before continuing. Setup installs the bundled GSI file and command bridge cfg files, and creates or appends a managed `autoexec.cfg` include. Steam launch options are not required.

In the GUI:

1. Choose or create a profile from the top bar.
2. Select a keyboard input device in Shared Settings, or leave it on auto-detect.
3. Configure GSI host/port if GSI is enabled.
4. Enable and tune individual component tabs.
5. Click `Save` to persist the profile and `Apply` to restart runtime configuration.
6. Use `Stop All` to stop running components and the GSI server.

## Configuration

Profiles are stored as JSON files under `profiles/`. The included `profiles/Default.json` shows the current profile shape:

```json
{
    "name": "Default",
    "app": {
        "gsi": {
            "enabled": true,
            "host": "127.0.0.1",
            "port": 3000
        },
        "shared": {
            "keyboard_device_path": "/dev/input/event3",
            "game_sensitivity": 1.0,
            "game_resolution": {"width": 1600, "height": 1200}
        }
    },
    "components": {}
}
```

### Profiles

`ProfileStore` reads and writes `profiles/<name>.json`. Profile names are sanitized to letters, numbers, underscores, and hyphens before the file path is built. If no profile exists, a default profile is created from `app/defaults.py`.

The top bar supports:

- New profile
- Duplicate profile
- Delete profile, except `Default`
- Save profile
- Apply profile
- Refresh Devices
- Stop All

### Shared Settings

Shared settings live at `app.shared` in each profile.

- `keyboard_device_path`: used by keyboard-based features. The Shared Settings tab can auto-detect or select a Linux keyboard device discovered by `DeviceService`.
- `game_sensitivity`: used by recoil and CV trigger sensitivity scaling.
- `game_resolution`: in-game resolution used by recoil/CV screen-space scaling.

`RuntimeManager` injects the shared keyboard device into Bhop, Snap Tap, and Counter Strafe. It injects the shared game sensitivity and game resolution into Recoil and CV Trigger runtime configuration. CV Trigger monitor capture uses the primary monitor resolution detected from the platform layer, with `top = 0` and `left = 0`.

### GSI

GSI settings live at `app.gsi` in each profile.

- `enabled`: starts or disables the local GSI server.
- `host`: default `127.0.0.1`.
- `port`: default `3000`.

When GSI is enabled, `RuntimeManager` keeps automation gated until GSI reports that the player is alive. `GSIServer` accepts JSON POST requests, parses weapon, ammo, health, round phase, and map data into `GameState`, then dispatches that state to components.

When GSI is disabled, the runtime gate is opened without waiting for GSI state.

### CS2 cfg setup

The setup window stores the accepted CS2 root in `profiles/settings.json`. Given a root folder, the cfg folder must be at `game/csgo/cfg`.

Setup writes these files into CS2's cfg folder:

- `gamestate_integration_cs2_assist.cfg`: copied from `resources/cfg/gsi.cfg`.
- `cs2assist_bootstrap.cfg`: binds hidden F13-F24 command slots.
- `cs2assist_cmd_01.cfg` through `cs2assist_cmd_12.cfg`: command slots written by the app at runtime.
- `autoexec.cfg`: receives one managed `exec cs2assist_bootstrap` block. If an existing `autoexec.cfg` is modified for the first time, it is backed up as `autoexec.cfg.cs2assist.bak`.

The managed autoexec block is idempotent; running setup again updates the block without duplicating it.

### Components

Component settings live under `components` in each profile.

- `bhop`: Linux keyboard component for space-bar bhop behavior. It uses the configured keyboard device and `tap_interval_ms`.
- `snap_tap`: Linux keyboard component for W/A/S/D last-key movement behavior.
- `counter_strafe`: Linux keyboard component with counter-strafe timing settings such as base, full-speed, min/max, shift/ctrl factors, curve, and manual brake windows.
- `long_jump`: Linux keyboard component that watches the configured key and sends CS2 console commands through the cfg command bridge for the jump/duck long-jump sequence.
- `recoil`: Mouse recoil control using `resources/mouse_patterns.json`, GSI weapon state when available, sensitivity scaling, movement frequency, axis strength, optional noise, return-mouse behavior, and an optional bullet overlay.
- `pixel_trigger`: Screen-pixel based trigger component using `mss`, a hold key, color-change threshold, click delay, cooldown, polling interval, monitor index, optional fixed coordinates, debug, and dry-run settings.
- `cv_trigger`: Computer-vision trigger/aim component using `resources/checkpoint.pt`, automatic monitor capture sizing, shared game-resolution settings, target-side settings, inference thresholds, smoothing/prediction values, global anti-oscillation settings, a global aim curve library, and per-rule activation/weapon/target/click settings.

#### CV Trigger Aim Assist Tuning

CV Trigger aim movement is configured with a global `aim_curves` library plus per-rule scalar tuning. Each curve is a named list of normalized points where `x = 0.0` means the crosshair is on the target and `x = 1.0` means the target is at that rule's `SNAP_DISTANCE`. The curve `y` value is a normalized speed shape, then the runtime scales it by the rule's `MAX_AIM_SPEED_PX` and scalar `AIM_STRENGTH`.

Each rule selects one global curve with `AIM_CURVE_ID` and keeps its own `SNAP_DISTANCE`, `MAX_AIM_SPEED_PX`, `AIM_STRENGTH`, and `NOISE_AMOUNT`. `AIM_STRENGTH` is a scalar: `0.0` disables aim movement, `0.5` is moderate, `1.0` is full baseline strength, and values above `1.0` are allowed for stronger movement. Noise is applied inside the no-overshoot motion engine so emitted movement cannot cross past the target.

Anti-oscillation settings are global to CV Trigger, not per-rule. `anti_oscillation_radius_px` enables near-target stability behavior, `anti_oscillation_reserve_counts` keeps a small count margin near the target, and `anti_oscillation_lock_frames` briefly suppresses movement after a near-target raw-error sign reversal.

The built-in constant, linear, and exponential entries are editable curve templates in `aim_curves`; they are not separate runtime response modes. Current profiles should use `AIM_CURVE_ID` and `MAX_AIM_SPEED_PX` rather than legacy response-curve keys.

Automated checks for this area can be run from the project root:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python tests/test_cv_rule_editor_config.py -v
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python tests/test_cv_trigger_editor_curves.py -v
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python tests/test_shared_settings_tab.py -v
PYTHONPATH=. python tests/test_cv_trigger_config_migration.py -v
PYTHONPATH=. python tests/test_cv_trigger_aim_motion.py -v
PYTHONPATH=. python tests/test_runtime_shared_config.py -v
```

## Architecture

- `app/main.py`: GUI entrypoint. Creates `QApplication`, runs CS2 setup when needed, applies style, constructs `MainWindow`, and starts the event loop.
- `app/cs2_integration/`: validates CS2 game roots, installs cfg files, stores app-level setup settings, and writes command-slot cfg files for console command execution.
- `app/ui/main_window.py`: main UI controller. Builds the profile toolbar, tab widget, log view, shared settings tab, GSI tab, and component tabs.
- `app/runtime.py`: owns `RuntimeManager`, creates component instances, applies profile configuration, starts/stops components, configures GSI, and forwards GSI state.
- `app/gsi.py`: implements `GSIServer` and `GameState`. The server runs a threaded HTTP listener and handles JSON POST payloads from CS2 GSI.
- `app/profile_store.py`: implements `ProfileStore` for creating, loading, saving, listing, and deleting JSON profiles.
- `app/device_service.py`: lists Linux keyboard devices through `evdev` and monitor geometry through `mss`.
- `app/platform/linux_input.py`: shared Linux keyboard hub built on `evdev` and `uinput`; used by keyboard-filtering components.
- `app/components/`: component implementations for Bhop, Snap Tap, Counter Strafe, Long Jump, Recoil Control, Pixel Trigger, and CV Trigger.
- `app/ui/tabs/`: Qt tabs for Shared Settings, GSI, and component configuration.
- `app/ui/widgets/`: reusable widgets such as component editors, CV rule editors, log bridge, collapsible boxes, and bullet overlay.

The runtime flow is:

1. `MainWindow` loads a profile through `ProfileStore`.
2. UI widgets edit the profile dictionary.
3. Saving writes the profile JSON back to `profiles/`.
4. Applying calls `RuntimeManager.configure_all()`, `RuntimeManager.configure_gsi()`, and `RuntimeManager.apply_enabled_states()`.
5. `RuntimeManager` starts enabled components and gates automation from GSI state when GSI is enabled.

## Troubleshooting

### uinput permission denied

Symptoms include errors when creating virtual keyboards or virtual mice, or components reporting that Linux `evdev/uinput` is unavailable.

Check that `uinput` is loaded:

```bash
lsmod | grep uinput
```

If it is missing, load it:

```bash
sudo modprobe uinput
```

Check permissions for `/dev/uinput` and the selected `/dev/input/event*` keyboard device. If your user cannot read the keyboard event device or write to `uinput`, update udev rules and group membership as shown in [Installation](#installation), then log out and back in.

### GSI not receiving data

The GSI tab shows the last state received from the local GSI server. If it stays at `No data yet.`:

- Confirm GSI is enabled in the profile.
- Confirm the host and port match the CS2 GSI configuration.
- Confirm nothing else is using the configured port.
- Apply the profile again and check the log for `GSI listening on http://<host>:<port>` or `Failed to start GSI server`.
- Remember that when GSI is enabled, features stay gated until GSI reports the player is alive.

### setup says cfg folder not found

The setup window expects the Counter-Strike 2 game root, not the cfg folder itself. The selected folder must contain `game/csgo/cfg`.

### commands or Long Jump do not run in game

Confirm setup completed successfully and that CS2 has loaded `autoexec.cfg`. The cfg folder should contain `cs2assist_bootstrap.cfg` and `cs2assist_cmd_07.cfg`. If CS2 was already running during first setup, restart CS2 so `autoexec.cfg` can execute the managed bootstrap include.

### model not found

CV Trigger requires the model path configured at `components.cv_trigger.model_path`. The default project resource is `resources/checkpoint.pt`, and `profiles/Default.json` points to that file in this checkout.

If the log reports `Model not found`, update the CV Trigger model path in the profile or restore the missing model file.

### device not detected

The Shared Settings tab lists keyboard devices discovered by `DeviceService` using `evdev`. If the list is empty or the expected keyboard is missing:

- Confirm the application is running on Linux.
- Confirm `evdev` is installed from `requirements.txt`.
- Confirm your user can read `/dev/input/event*` devices.
- Click `Refresh Devices` after changing permissions or reconnecting hardware.
- Use Auto-detect if the selected saved device path no longer exists.

## License

No license file is present in this repository. Add a license file before distributing or reusing the project under specific license terms.
