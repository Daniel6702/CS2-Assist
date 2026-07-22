from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .activation import canonical_weapon_name


WEAPON_RECOIL_FILE: Final = Path(__file__).resolve().parents[3] / "resources" / "weapons_data" / "cs2_weapon_fire_rate_recoil.csv"
FAST_AUTOMATIC_MAX_INTERVAL_MS: Final = 130.0
HIGH_RECOIL_AUTOMATIC_MIN_AMOUNT: Final = 25.0
EARLY_SPRAY_HOLD_INTERVALS: Final = 2.0


@dataclass(frozen=True, slots=True)
class WeaponRecoilInfo:
    weapon_name: str
    weapon_code: str
    fire_rate_rpm: float
    recoil_amount: float

    @property
    def fire_interval_ms(self) -> float:
        if self.fire_rate_rpm <= 0.0:
            return 0.0
        return 60_000.0 / self.fire_rate_rpm


@dataclass(frozen=True, slots=True)
class PostShotTimingConfig:
    fallback_hold_ms: int = 90
    fallback_restore_ms: int = 130
    recoil_hold_ms_per_amount: float = 1.2
    recoil_restore_ms_per_amount: float = 0.8
    fire_interval_hold_fraction: float = 0.4
    fire_interval_restore_fraction: float = 0.2
    min_hold_ms: int = 50
    max_hold_ms: int = 240
    min_restore_ms: int = 80
    max_restore_ms: int = 260


def load_weapon_recoil_table(path: Path = WEAPON_RECOIL_FILE) -> dict[str, WeaponRecoilInfo]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return {}

    table: dict[str, WeaponRecoilInfo] = {}
    for row in rows:
        info = _parse_row(row)
        if info is None:
            continue
        table[canonical_weapon_name(info.weapon_code)] = info
    return table


def weapon_recoil_info(table: dict[str, WeaponRecoilInfo], weapon_name: str | None) -> WeaponRecoilInfo | None:
    if not weapon_name:
        return None
    return table.get(canonical_weapon_name(weapon_name))


def hold_restore_timing_ms(info: WeaponRecoilInfo | None, config: PostShotTimingConfig) -> tuple[int, int]:
    if info is None:
        return max(0, int(config.fallback_hold_ms)), max(0, int(config.fallback_restore_ms))

    hold = info.recoil_amount * config.recoil_hold_ms_per_amount
    hold += info.fire_interval_ms * config.fire_interval_hold_fraction
    if (
        config.recoil_hold_ms_per_amount > 0.0
        and info.fire_interval_ms <= FAST_AUTOMATIC_MAX_INTERVAL_MS
        and info.recoil_amount >= HIGH_RECOIL_AUTOMATIC_MIN_AMOUNT
    ):
        hold = max(hold, info.fire_interval_ms * EARLY_SPRAY_HOLD_INTERVALS)
    restore = info.recoil_amount * config.recoil_restore_ms_per_amount
    restore += info.fire_interval_ms * config.fire_interval_restore_fraction
    return (
        _clamp_int(round(hold), config.min_hold_ms, config.max_hold_ms),
        _clamp_int(round(restore), config.min_restore_ms, config.max_restore_ms),
    )


def _parse_row(row: dict[str, str | None]) -> WeaponRecoilInfo | None:
    weapon_name = (row.get("weapon_name") or "").strip()
    weapon_code = (row.get("weapon_code") or "").strip()
    if not weapon_name or not weapon_code:
        return None
    try:
        fire_rate_rpm = float(row.get("fire_rate_rpm") or "")
        recoil_amount = float(row.get("recoil_amount") or "")
    except ValueError:
        return None
    return WeaponRecoilInfo(
        weapon_name=weapon_name,
        weapon_code=weapon_code,
        fire_rate_rpm=fire_rate_rpm,
        recoil_amount=recoil_amount,
    )


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    lo = min(minimum, maximum)
    hi = max(minimum, maximum)
    return max(lo, min(hi, int(value)))
