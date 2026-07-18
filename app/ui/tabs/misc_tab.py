from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from app.ui.tabs.base import BaseTab


class MiscTab(BaseTab):
    """Combined tab for Kill Sound + Bomb Timer settings."""

    config_changed = QtCore.Signal(str, dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # ── Kill Sound ────────────────────────────────────────────────
        self._build_kill_sound(outer)

        # ── Bomb Timer ────────────────────────────────────────────────
        self._build_bomb_timer(outer)

        outer.addStretch(1)

    # ==================================================================
    #  Kill Sound UI
    # ==================================================================

    def _build_kill_sound(self, parent: QtWidgets.QVBoxLayout) -> None:
        group = QtWidgets.QGroupBox("Kill Sound")
        group.setStyleSheet("QGroupBox { font-weight: 600; }")
        form = QtWidgets.QFormLayout(group)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        parent.addWidget(group)

        self.ks_enabled = QtWidgets.QCheckBox()
        self.ks_enabled.stateChanged.connect(self._emit_kill_sound)
        form.addRow("Enabled", self.ks_enabled)

        file_row = QtWidgets.QHBoxLayout()
        self.ks_file = QtWidgets.QLineEdit()
        self.ks_file.setPlaceholderText("Select a sound file (.mp3, .wav, .ogg …)")
        self.ks_file.editingFinished.connect(self._emit_kill_sound)
        file_row.addWidget(self.ks_file, 1)
        browse_btn = QtWidgets.QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_kill_sound)
        file_row.addWidget(browse_btn)
        form.addRow("Sound file", file_row)

        self.ks_volume = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.ks_volume.setRange(0, 100)
        self.ks_volume.setValue(50)
        self.ks_volume.valueChanged.connect(self._emit_kill_sound)
        self.ks_vol_label = QtWidgets.QLabel("50%")
        self.ks_volume.valueChanged.connect(lambda v: self.ks_vol_label.setText(f"{v}%"))
        vol_row = QtWidgets.QHBoxLayout()
        vol_row.addWidget(self.ks_volume, 1)
        vol_row.addWidget(self.ks_vol_label)
        form.addRow("Volume", vol_row)

        test_btn = QtWidgets.QPushButton("Test Sound")
        test_btn.clicked.connect(self._test_kill_sound)
        form.addRow("", test_btn)

        help_lbl = QtWidgets.QLabel(
            "Requires GSI to be enabled.  Plays when a kill is recorded via GSI."
        )
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: #666;")
        parent.addWidget(help_lbl)

    def _browse_kill_sound(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Kill Sound",
            "",
            "Audio Files (*.mp3 *.wav *.ogg *.flac *.aac);;All Files (*)",
        )
        if path:
            self.ks_file.setText(path)
            self._emit_kill_sound()

    def _test_kill_sound(self) -> None:
        from app.components.kill_sound import KillSoundComponent

        path = self.ks_file.text().strip()
        if not path:
            return
        KillSoundComponent._play(path, self.ks_volume.value())

    def _emit_kill_sound(self) -> None:
        self.config_changed.emit("kill_sound", self._kill_sound_config())

    def _kill_sound_config(self) -> dict[str, Any]:
        return {
            "enabled": self.ks_enabled.isChecked(),
            "sound_file": self.ks_file.text().strip(),
            "volume": self.ks_volume.value(),
        }

    # ==================================================================
    #  Bomb Timer UI
    # ==================================================================

    def _build_bomb_timer(self, parent: QtWidgets.QVBoxLayout) -> None:
        group = QtWidgets.QGroupBox("Bomb Timer")
        group.setStyleSheet("QGroupBox { font-weight: 600; }")
        outer = QtWidgets.QVBoxLayout(group)
        outer.setSpacing(6)
        parent.addWidget(group)

        # Enabled
        self.bt_enabled = QtWidgets.QCheckBox("Enabled")
        self.bt_enabled.stateChanged.connect(self._emit_bomb_timer)
        outer.addWidget(self.bt_enabled)

        # Overlay font size
        size_row = QtWidgets.QHBoxLayout()
        self.bt_font_size = QtWidgets.QSpinBox()
        self.bt_font_size.setRange(12, 200)
        self.bt_font_size.setValue(48)
        self.bt_font_size.valueChanged.connect(self._emit_bomb_timer)
        size_row.addWidget(QtWidgets.QLabel("Font size:"))
        size_row.addWidget(self.bt_font_size)
        size_row.addStretch(1)
        outer.addLayout(size_row)

        # Overlay colour
        color_row = QtWidgets.QHBoxLayout()
        self.bt_color_btn = QtWidgets.QPushButton()
        self.bt_color_btn.setFixedSize(32, 24)
        self.bt_color_btn.clicked.connect(self._pick_bomb_color)
        self._bt_color = QtGui.QColor(255, 50, 50)
        self._update_color_button()
        color_row.addWidget(QtWidgets.QLabel("Text colour:"))
        color_row.addWidget(self.bt_color_btn)
        color_row.addStretch(1)
        outer.addLayout(color_row)

        # Defuse warning
        self.bt_defuse_warn = QtWidgets.QCheckBox("CT defuse out-of-time warning")
        self.bt_defuse_warn.setChecked(True)
        self.bt_defuse_warn.stateChanged.connect(self._emit_bomb_timer)
        outer.addWidget(self.bt_defuse_warn)

        # Warning sounds
        outer.addWidget(QtWidgets.QLabel("Warning sounds:"))
        self._build_warning_sound(
            outer,
            label="10 seconds remaining",
            enabled_attr="bt_warn10_enabled",
            file_attr="bt_warn10_file",
            vol_attr="bt_warn10_volume",
            vol_label_attr="bt_warn10_vol_label",
            browse_callback=self._browse_10s,
        )
        self._build_warning_sound(
            outer,
            label="5 seconds remaining",
            enabled_attr="bt_warn5_enabled",
            file_attr="bt_warn5_file",
            vol_attr="bt_warn5_volume",
            vol_label_attr="bt_warn5_vol_label",
            browse_callback=self._browse_5s,
        )

    def _build_warning_sound(
        self,
        parent: QtWidgets.QVBoxLayout,
        *,
        label: str,
        enabled_attr: str,
        file_attr: str,
        vol_attr: str,
        vol_label_attr: str,
        browse_callback,
    ) -> None:
        row = QtWidgets.QHBoxLayout()
        cb = QtWidgets.QCheckBox(label)
        cb.stateChanged.connect(self._emit_bomb_timer)
        setattr(self, enabled_attr, cb)
        row.addWidget(cb)

        le = QtWidgets.QLineEdit()
        le.setPlaceholderText("Sound file …")
        le.editingFinished.connect(self._emit_bomb_timer)
        setattr(self, file_attr, le)
        row.addWidget(le, 1)

        btn = QtWidgets.QPushButton("Browse…")
        btn.clicked.connect(browse_callback)
        row.addWidget(btn)

        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(50)
        slider.valueChanged.connect(self._emit_bomb_timer)
        lbl = QtWidgets.QLabel("50%")
        slider.valueChanged.connect(lambda v, l=lbl: l.setText(f"{v}%"))
        setattr(self, vol_attr, slider)
        setattr(self, vol_label_attr, lbl)
        row.addWidget(slider)
        row.addWidget(lbl)

        parent.addLayout(row)

    def _browse_10s(self) -> None:
        self._browse_warning("Select 10s Warning Sound", self.bt_warn10_file)

    def _browse_5s(self) -> None:
        self._browse_warning("Select 5s Warning Sound", self.bt_warn5_file)

    def _browse_warning(self, title: str, target: QtWidgets.QLineEdit) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, title, "", "Audio Files (*.mp3 *.wav *.ogg *.flac *.aac);;All Files (*)"
        )
        if path:
            target.setText(path)
            self._emit_bomb_timer()

    def _pick_bomb_color(self) -> None:
        color = QtWidgets.QColorDialog.getColor(self._bt_color, self, "Select Timer Colour")
        if color.isValid():
            self._bt_color = color
            self._update_color_button()
            self._emit_bomb_timer()

    def _update_color_button(self) -> None:
        self.bt_color_btn.setStyleSheet(
            f"background-color: {self._bt_color.name()}; border: 1px solid #888;"
        )

    def _emit_bomb_timer(self) -> None:
        self.config_changed.emit("bomb_timer", self._bomb_timer_config())

    def _bomb_timer_config(self) -> dict[str, Any]:
        return {
            "enabled": self.bt_enabled.isChecked(),
            "defuse_warning_enabled": self.bt_defuse_warn.isChecked(),
            "overlay_font_size": self.bt_font_size.value(),
            "overlay_color": self._bt_color.name(),
            "warning_10s_enabled": self.bt_warn10_enabled.isChecked(),
            "warning_10s_file": self.bt_warn10_file.text().strip(),
            "warning_10s_volume": self.bt_warn10_volume.value(),
            "warning_5s_enabled": self.bt_warn5_enabled.isChecked(),
            "warning_5s_file": self.bt_warn5_file.text().strip(),
            "warning_5s_volume": self.bt_warn5_volume.value(),
        }

    # ==================================================================
    #  BaseTab interface
    # ==================================================================

    def load_config(self, section_name: str, config: dict[str, Any]) -> None:
        """Load config for *section_name* ('kill_sound' or 'bomb_timer')."""
        if section_name == "kill_sound":
            self.ks_enabled.setChecked(bool(config.get("enabled", False)))
            self.ks_file.setText(str(config.get("sound_file", "") or ""))
            vol = int(config.get("volume", 50))
            self.ks_volume.setValue(max(0, min(100, vol)))
        elif section_name == "bomb_timer":
            self.bt_enabled.setChecked(bool(config.get("enabled", False)))
            self.bt_defuse_warn.setChecked(bool(config.get("defuse_warning_enabled", True)))
            self.bt_font_size.setValue(int(config.get("overlay_font_size", 48)))
            raw_color = config.get("overlay_color", "#FF3232")
            if isinstance(raw_color, str):
                self._bt_color = QtGui.QColor(raw_color)
            self._update_color_button()

            self.bt_warn10_enabled.setChecked(bool(config.get("warning_10s_enabled", True)))
            self.bt_warn10_file.setText(str(config.get("warning_10s_file", "") or ""))
            v10 = int(config.get("warning_10s_volume", 50))
            self.bt_warn10_volume.setValue(max(0, min(100, v10)))

            self.bt_warn5_enabled.setChecked(bool(config.get("warning_5s_enabled", True)))
            self.bt_warn5_file.setText(str(config.get("warning_5s_file", "") or ""))
            v5 = int(config.get("warning_5s_volume", 50))
            self.bt_warn5_volume.setValue(max(0, min(100, v5)))

    def extract_config(self) -> dict[str, dict[str, Any]]:
        return {
            "kill_sound": self._kill_sound_config(),
            "bomb_timer": self._bomb_timer_config(),
        }
