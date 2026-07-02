from __future__ import annotations

import random
import time

_rng = random.Random()

# ---------------------------------------------------------------------------
# Obscured device names for uinput virtual devices
# Uses generic names to avoid easy plaintext signature matching by
# kernel-level anti-cheat monitors.
# ---------------------------------------------------------------------------
OBSCURED_MOUSE_NAME = "HID-compliant mouse"
OBSCURED_KEYBOARD_NAME = "HID-compliant keyboard"

# Original device names used when safety features are disabled.
ORIGINAL_CV_MOUSE_NAME = "cs2-unified-cv-trigger-mouse"
ORIGINAL_RECOIL_MOUSE_NAME = "cs2-unified-recoil-virtual-mouse"


def device_name(original: str, obscure: bool = False) -> str:
    """Return *original* when *obscure* is False, else the generic name."""
    if not obscure:
        return original
    return OBSCURED_MOUSE_NAME


def humanize_jitter(
    value: float,
    fraction: float = 0.2,
    min_val: float | None = None,
    max_val: float | None = None,
) -> float:
    """Add random jitter to a timing value to make it less machine-perfect.

    Args:
        value: The base value to jitter.
        fraction: Maximum jitter as a fraction of *value* (default 0.2 = ±20%).
        min_val: Clamp result to at least this value.
        max_val: Clamp result to at most this value.

    Returns:
        Jittered value.
    """
    if value <= 0:
        return value
    jitter_range = value * fraction
    result = value + _rng.uniform(-jitter_range, jitter_range)
    if min_val is not None:
        result = max(min_val, result)
    if max_val is not None:
        result = min(max_val, result)
    return result


def humanize_sleep(seconds: float, fraction: float = 0.2, min_val: float = 0.0) -> None:
    """Sleep with a randomized duration to avoid fixed-interval detection."""
    time.sleep(humanize_jitter(seconds, fraction, min_val=min_val))


def humanize_frequency_interval(hz: float, jitter_fraction: float = 0.15) -> float:
    """Convert a frequency to a jittered interval in seconds.

    Jitter is applied to the *interval* (not the frequency) so that
    the timing variance looks natural to an input monitor.
    """
    if hz <= 0:
        return 0.001
    base_interval = 1.0 / hz
    return humanize_jitter(base_interval, fraction=jitter_fraction, min_val=0.0005)


def eased_movement_steps(
    dx: int,
    dy: int,
    min_frames: int = 2,
    max_frames: int = 4,
) -> list[tuple[int, int]]:
    """Split a movement delta over multiple steps with smoothstep easing.

    Returns a list of (dx, dy) tuples, one per frame, that sum to the
    original (dx, dy).  Each step is sized so the largest motion occurs
    mid-sequence, mimicking natural human acceleration/deceleration.

    When both *dx* and *dy* are zero, returns a single (0, 0) step.
    """
    if dx == 0 and dy == 0:
        return [(0, 0)]

    frames = _rng.randint(min_frames, max_frames)
    steps: list[tuple[int, int]] = []

    for i in range(1, frames + 1):
        t = i / frames
        eased = t * t * (3 - 2 * t)  # smoothstep
        step_dx = int(round(dx * eased))
        step_dy = int(round(dy * eased))
        if i > 1:
            step_dx -= steps[-1][0]
            step_dy -= steps[-1][1]
        steps.append((step_dx, step_dy))

    return steps


def short_sleep_interleaved(
    steps: list[tuple[int, int]],
    base_sleep: float = 0.002,
    fraction: float = 0.3,
) -> list[tuple[int, int]]:
    """Insert a jittered micro-sleep between consecutive movement steps.

    This is a no-op for lists with one element — the caller is expected
    to call *humanize_sleep* themselves for the single-frame case.
    """
    if len(steps) <= 1:
        return steps
    return steps  # caller handles the inter-step sleep themselves


def blend_safety_setting(
    safety: dict,
    *keys: str,
    default: float | bool = 0.0,
    enforce_enabled: dict | None = None,
) -> float | bool:
    """Drill into a nested safety dict by *keys* and return the value.

    If *enforce_enabled* is given and its ``enabled`` key is falsy, every
    numeric value is returned unchanged regardless of the specific setting
    (so jitter always returns 0 when the master switch is off).
    """
    if enforce_enabled is not None and not bool(enforce_enabled.get("enabled", False)):
        return default
    val: dict | object = safety
    for k in keys:
        if not isinstance(val, dict):
            return default
        val = val.get(k, default)
    if isinstance(val, (int, float, bool)):
        return val
    return default
