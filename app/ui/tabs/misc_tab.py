from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from app.ui.tabs.base import BaseTab
from app.ui.widgets.auto_accept_section import AutoAcceptSection
from app.ui.widgets.auto_shoot_section import AutoShootSection
from app.ui.widgets.bomb_timer_section import BombTimerSection
from app.ui.widgets.defuse_warning_section import DefuseWarningSection
from app.ui.widgets.flash_filter_section import FlashFilterSection
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
        self.defuse_warning = DefuseWarningSection()
        self.auto_accept = AutoAcceptSection()
        self.auto_shoot = AutoShootSection()
        self.flash_filter = FlashFilterSection()

        top_row = QtWidgets.QHBoxLayout()
        top_row.setSpacing(8)
        for section in (self.kill_sound, self.auto_shoot, self.flash_filter):
            top_row.addWidget(section, 1)
        outer.addLayout(top_row)

        auto_accept_row = QtWidgets.QHBoxLayout()
        auto_accept_row.setSpacing(8)
        auto_accept_row.addWidget(self.auto_accept, 1)
        outer.addLayout(auto_accept_row)

        timer_row = QtWidgets.QHBoxLayout()
        timer_row.setSpacing(8)
        timer_row.addWidget(self.bomb_timer, 1)
        timer_row.addWidget(self.defuse_warning, 1)
        outer.addLayout(timer_row)

        sections = (
            ("kill_sound", self.kill_sound),
            ("auto_accept", self.auto_accept),
            ("auto_shoot", self.auto_shoot),
            ("flash_filter", self.flash_filter),
        )
        for section_name, section in sections:
            section.changed.connect(lambda _checked=False, name=section_name: self._emit_section(name))
        self.bomb_timer.changed.connect(lambda: self._emit_section("bomb_timer"))
        self.defuse_warning.changed.connect(lambda: self._emit_section("bomb_timer"))
        outer.addStretch(1)

    def load_config(self, section_name: str, config: dict[str, Any]) -> None:
        if section_name == "bomb_timer":
            self.bomb_timer.load_config(config)
            self.defuse_warning.load_config(config)
            return
        section = self._sections().get(section_name)
        if section is not None:
            section.load_config(config)

    def extract_config(self) -> dict[str, dict[str, Any]]:
        return {
            "kill_sound": self.kill_sound.extract_config(),
            "bomb_timer": {
                **self.bomb_timer.extract_config(),
                **self.defuse_warning.extract_config(),
            },
            "auto_accept": self.auto_accept.extract_config(),
            "auto_shoot": self.auto_shoot.extract_config(),
            "flash_filter": self.flash_filter.extract_config(),
        }

    def _emit_section(self, section_name: str) -> None:
        if section_name == "bomb_timer":
            self.config_changed.emit(section_name, self.extract_config()[section_name])
            return
        section = self._sections()[section_name]
        self.config_changed.emit(section_name, section.extract_config())

    def _sections(self) -> dict[str, KillSoundSection | AutoAcceptSection | AutoShootSection | FlashFilterSection]:
        return {
            "kill_sound": self.kill_sound,
            "auto_accept": self.auto_accept,
            "auto_shoot": self.auto_shoot,
            "flash_filter": self.flash_filter,
        }
