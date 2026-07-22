from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from app.defaults import RESOURCES_DIR


COMMAND_SLOT_COUNT: Final[int] = 12
COMMAND_SLOT_PREFIX: Final[str] = "cs2assist_cmd_"
BOOTSTRAP_CFG_NAME: Final[str] = "cs2assist_bootstrap.cfg"
GSI_CFG_NAME: Final[str] = "gamestate_integration_cs2_assist.cfg"
AUTOEXEC_NAME: Final[str] = "autoexec.cfg"
AUTOEXEC_BACKUP_NAME: Final[str] = "autoexec.cfg.cs2assist.bak"
AUTOEXEC_BLOCK_BEGIN: Final[str] = "// >>> CS2 Assist managed block >>>"
AUTOEXEC_BLOCK_END: Final[str] = "// <<< CS2 Assist managed block <<<"


@dataclass(frozen=True, slots=True)
class InvalidGameRootError(Exception):
    root: Path
    cfg_dir: Path

    def __str__(self) -> str:
        return f"CS2 cfg folder not found: {self.cfg_dir}"


@dataclass(frozen=True, slots=True)
class CfgInstallResult:
    cfg_dir: Path
    gsi_path: Path
    bootstrap_path: Path
    autoexec_path: Path
    autoexec_backup_path: Path
    command_slot_paths: tuple[Path, ...]


def cfg_dir_for_game_root(root: Path) -> Path:
    return root / "game" / "csgo" / "cfg"


def validate_game_root(root: Path) -> Path:
    cfg_dir = cfg_dir_for_game_root(root)
    if not cfg_dir.is_dir():
        raise InvalidGameRootError(root=root, cfg_dir=cfg_dir)
    return cfg_dir


def command_slot_name(slot: int) -> str:
    return f"{COMMAND_SLOT_PREFIX}{slot:02d}.cfg"


def install_cfg_files(root: Path) -> CfgInstallResult:
    cfg_dir = validate_game_root(root)
    gsi_path = cfg_dir / GSI_CFG_NAME
    bootstrap_path = cfg_dir / BOOTSTRAP_CFG_NAME
    autoexec_path = cfg_dir / AUTOEXEC_NAME
    backup_path = cfg_dir / AUTOEXEC_BACKUP_NAME

    shutil.copyfile(RESOURCES_DIR / "cfg" / "gsi.cfg", gsi_path)
    shutil.copyfile(RESOURCES_DIR / "cfg" / BOOTSTRAP_CFG_NAME, bootstrap_path)

    slot_paths = tuple(cfg_dir / command_slot_name(slot) for slot in range(1, COMMAND_SLOT_COUNT + 1))
    for path in slot_paths:
        if not path.exists():
            path.write_text("")

    _update_autoexec(autoexec_path, backup_path)
    return CfgInstallResult(
        cfg_dir=cfg_dir,
        gsi_path=gsi_path,
        bootstrap_path=bootstrap_path,
        autoexec_path=autoexec_path,
        autoexec_backup_path=backup_path,
        command_slot_paths=slot_paths,
    )


def _managed_autoexec_block() -> str:
    return "\n".join(
        (
            AUTOEXEC_BLOCK_BEGIN,
            f"exec {Path(BOOTSTRAP_CFG_NAME).stem}",
            AUTOEXEC_BLOCK_END,
        ),
    )


def _update_autoexec(autoexec_path: Path, backup_path: Path) -> None:
    original = autoexec_path.read_text() if autoexec_path.exists() else ""
    if original and not backup_path.exists():
        backup_path.write_text(original)

    block = _managed_autoexec_block()
    start = original.find(AUTOEXEC_BLOCK_BEGIN)
    end = original.find(AUTOEXEC_BLOCK_END)
    if start >= 0 and end >= start:
        end += len(AUTOEXEC_BLOCK_END)
        updated = original[:start] + block + original[end:]
    else:
        separator = "" if not original or original.endswith("\n") else "\n"
        updated = f"{original}{separator}{block}\n"
    autoexec_path.write_text(updated)
