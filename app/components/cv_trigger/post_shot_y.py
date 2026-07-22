from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .activation import canonical_weapon_name
from .post_shot_config import (
    PostShotSuppressionConfig,
    default_post_shot_y_suppression_config,
    post_shot_config_from_mapping,
)
from .weapon_recoil import WeaponRecoilInfo, hold_restore_timing_ms


class ShotStartKind(Enum):
    PROVISIONAL = "provisional"
    GSI_ONLY = "gsi_only"

@dataclass(frozen=True, slots=True)
class ShotStartEvent:
    kind: ShotStartKind
    source: str
    weapon: str
    happened_at: float


@dataclass(frozen=True, slots=True)
class ConfirmedShotEvent:
    confirmed_from: ShotStartEvent
    weapon: str
    ammo_delta: int
    shots_fired: int | None
    first_in_mag: bool
    isolated: bool
    sustained: bool
    happened_at: float
    recoil_active: bool


@dataclass(frozen=True, slots=True)
class ShotTrackerUpdate:
    confirmed: ConfirmedShotEvent | None = None
    cancel_provisional: bool = False
    should_start_suppression: bool = False


class ShotEventTracker:
    def __init__(self, config: PostShotSuppressionConfig) -> None:
        self._config = config
        self._pending: ShotStartEvent | None = None
        self._weapon: str | None = None
        self._ammo_clip: int | None = None
        self._ammo_clip_max: int | None = None
        self._last_confirmed_at: float | None = None
        self._last_confirmed_weapon: str | None = None

    def note_manual_press(self, weapon: str | None, now: float) -> ShotStartEvent:
        return self._note_provisional("manual", weapon, now)

    def note_cv_auto_click(self, weapon: str | None, now: float) -> ShotStartEvent:
        return self._note_provisional("cv_auto", weapon, now)

    def update_gsi_weapon_ammo(
        self,
        weapon: str | None,
        ammo_clip: int | None,
        ammo_clip_max: int | None,
        now: float,
        recoil_active: bool = False,
    ) -> ShotTrackerUpdate:
        current_weapon = canonical_weapon_name(weapon)
        if not current_weapon or ammo_clip is None:
            return self._cancel_if_pending()

        if self._weapon is not None and current_weapon != self._weapon:
            self._set_gsi_state(current_weapon, ammo_clip, ammo_clip_max)
            return self._cancel_if_pending()

        if self._ammo_clip is None:
            self._set_gsi_state(current_weapon, ammo_clip, ammo_clip_max)
            return ShotTrackerUpdate()

        previous_ammo = self._ammo_clip
        self._set_gsi_state(current_weapon, ammo_clip, ammo_clip_max)

        if ammo_clip > previous_ammo:
            return self._cancel_if_pending()
        if ammo_clip == previous_ammo:
            return self._cancel_if_pending() if self._pending_is_stale(now) else ShotTrackerUpdate()

        return self._confirmed_update(
            weapon=current_weapon,
            previous_ammo=previous_ammo,
            ammo_clip=ammo_clip,
            ammo_clip_max=ammo_clip_max,
            now=now,
            recoil_active=recoil_active,
        )

    def reset(self) -> None:
        self._pending = None
        self._weapon = None
        self._ammo_clip = None
        self._ammo_clip_max = None
        self._last_confirmed_at = None
        self._last_confirmed_weapon = None

    def _note_provisional(self, source: str, weapon: str | None, now: float) -> ShotStartEvent:
        event = ShotStartEvent(
            kind=ShotStartKind.PROVISIONAL,
            source=source,
            weapon=canonical_weapon_name(weapon),
            happened_at=now,
        )
        self._pending = event
        return event

    def _confirmed_update(
        self,
        *,
        weapon: str,
        previous_ammo: int,
        ammo_clip: int,
        ammo_clip_max: int | None,
        now: float,
        recoil_active: bool,
    ) -> ShotTrackerUpdate:
        pending = self._pending if self._pending_matches(weapon, now) else None
        start_event = pending or ShotStartEvent(ShotStartKind.GSI_ONLY, "gsi", weapon, now)
        ammo_delta = previous_ammo - ammo_clip
        shots_fired = None if ammo_clip_max is None else max(0, ammo_clip_max - ammo_clip)
        first_in_mag = shots_fired is not None and shots_fired <= ammo_delta
        isolated = self._is_isolated(weapon, now)
        sustained = bool(recoil_active and shots_fired is not None and shots_fired >= self._config.sustained_shot_index and not isolated)
        confirmed = ConfirmedShotEvent(
            confirmed_from=start_event,
            weapon=weapon,
            ammo_delta=ammo_delta,
            shots_fired=shots_fired,
            first_in_mag=first_in_mag,
            isolated=isolated,
            sustained=sustained,
            happened_at=now,
            recoil_active=recoil_active,
        )
        self._pending = None
        self._last_confirmed_at = now
        self._last_confirmed_weapon = weapon
        should_start = (pending is not None or first_in_mag or isolated) and not sustained
        return ShotTrackerUpdate(confirmed=confirmed, should_start_suppression=should_start)

    def _set_gsi_state(self, weapon: str, ammo_clip: int, ammo_clip_max: int | None) -> None:
        self._weapon = weapon
        self._ammo_clip = ammo_clip
        self._ammo_clip_max = ammo_clip_max

    def _pending_matches(self, weapon: str, now: float) -> bool:
        pending = self._pending
        if pending is None:
            return False
        return pending.weapon == weapon and not self._pending_is_stale(now)

    def _pending_is_stale(self, now: float) -> bool:
        pending = self._pending
        if pending is None:
            return False
        elapsed_ms = (now - pending.happened_at) * 1000.0
        return elapsed_ms > self._config.candidate_validation_window_ms

    def _cancel_if_pending(self) -> ShotTrackerUpdate:
        had_pending = self._pending is not None
        self._pending = None
        return ShotTrackerUpdate(cancel_provisional=had_pending)

    def _is_isolated(self, weapon: str, now: float) -> bool:
        if self._last_confirmed_at is None or self._last_confirmed_weapon != weapon:
            return True
        elapsed_ms = (now - self._last_confirmed_at) * 1000.0
        return elapsed_ms >= self._config.isolated_gap_ms


class PostShotYSuppression:
    def __init__(self, config: PostShotSuppressionConfig) -> None:
        self._config = config
        self._started_at: float | None = None
        self._hold_until = 0.0
        self._restore_until = 0.0
        self._missing_since: float | None = None

    def start(self, event: ShotStartEvent | ConfirmedShotEvent, info: WeaponRecoilInfo | None) -> None:
        if not self._config.enabled:
            return
        started_at = event.happened_at
        hold_ms, restore_ms = hold_restore_timing_ms(info, self._config)
        strength = max(0.0, self._config.stabilization_strength)
        hold_ms = round((hold_ms + restore_ms) * strength)
        restore_ms = 0
        self._started_at = started_at
        self._hold_until = started_at + hold_ms / 1000.0
        self._restore_until = self._hold_until + restore_ms / 1000.0
        self._missing_since = None

    def apply_y(self, dy: float, now: float, recoil_active: bool) -> float:
        if dy <= 0.0:
            return dy
        return dy * self.y_scale_for(now, recoil_active)

    def apply_x(self, dx: float, now: float) -> float:
        return dx * self.x_scale_for(now)

    def y_scale_for(self, now: float, recoil_active: bool) -> float:
        scale = self._window_scale(now, self._config.stabilization_strength)
        if recoil_active:
            return min(scale, _clamp_float(self._config.recoil_active_downward_scale, 0.0, 1.0))
        return scale

    def x_scale_for(self, now: float) -> float:
        return self._window_scale(now, self._config.horizontal_stabilization_strength)

    def active_at(self, now: float) -> bool:
        return self._started_at is not None and now < self._restore_until

    def note_target_visible(self) -> None:
        self._missing_since = None

    def note_target_missing(self, now: float) -> None:
        return

    def reset(self) -> None:
        self._started_at = None
        self._hold_until = 0.0
        self._restore_until = 0.0
        self._missing_since = None

    def _window_scale(self, now: float, strength: float) -> float:
        if not self.active_at(now):
            return 1.0
        strength = max(0.0, strength)
        floor = _clamp_float(1.0 - (0.98 * strength), 0.0, 1.0)
        if now <= self._hold_until:
            return floor
        span = self._restore_until - self._hold_until
        if span <= 0.0:
            return 1.0
        progress = _clamp_float((now - self._hold_until) / span, 0.0, 1.0)
        eased = progress * progress * (3.0 - 2.0 * progress)
        return floor + (1.0 - floor) * eased


def clamp_positive_y_to_limit(smoothed_y: float, limited_y: float) -> float:
    if smoothed_y <= 0.0:
        return smoothed_y
    return min(smoothed_y, max(0.0, limited_y))


def clamp_x_to_limit(smoothed_x: float, limited_x: float) -> float:
    limit = abs(limited_x)
    if smoothed_x > 0.0:
        return min(smoothed_x, limit)
    if smoothed_x < 0.0:
        return max(smoothed_x, -limit)
    return smoothed_x


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    if math.isnan(value):
        return minimum
    return max(minimum, min(maximum, value))
