from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from app.ui.tabs.base import BaseTab
from app.ui.widgets.auto_shoot_section import AutoShootSection
from app.ui.widgets.bomb_timer_section import BombTimerSection
from app.ui.widgets.kill_sound_section import KillSoundSection


class MiscTab(BaseTab):
    config_changed = QtCore.Signal(str, dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        self.kill_sound = KillSoundSection()
        self.bomb_timer = BombTimerSection()
        self.auto_shoot = AutoShootSection()

        sections = (
            ("kill_sound", self.kill_sound),
            ("bomb_timer", self.bomb_timer),
            ("auto_shoot", self.auto_shoot),
        )
        for section_name, section in sections:
            section.changed.connect(lambda _checked=False, name=section_name: self._emit_section(name))
            outer.addWidget(section)
        outer.addStretch(1)

    def load_config(self, section_name: str, config: dict[str, Any]) -> None:
        section = self._sections().get(section_name)
        if section is not None:
            section.load_config(config)

    def extract_config(self) -> dict[str, dict[str, Any]]:
        return {
            "kill_sound": self.kill_sound.extract_config(),
            "bomb_timer": self.bomb_timer.extract_config(),
            "auto_shoot": self.auto_shoot.extract_config(),
        }

    def _emit_section(self, section_name: str) -> None:
        section = self._sections()[section_name]
        self.config_changed.emit(section_name, section.extract_config())

    def _sections(self) -> dict[str, KillSoundSection | BombTimerSection | AutoShootSection]:
        return {
            "kill_sound": self.kill_sound,
            "bomb_timer": self.bomb_timer,
            "auto_shoot": self.auto_shoot,
        }
