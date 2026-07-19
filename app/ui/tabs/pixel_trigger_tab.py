"""Pixel Trigger tab — crosshair visualizer with pixel-accurate monitoring setup."""
from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Any

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QTimer, Signal

from app.device_service import DeviceService
from app.ui.tabs.base import BaseTab
from app.ui.widgets.crosshair_codec import CS2CrosshairCodec
from app.ui.widgets.crosshair_grid_widget import PixelGridWidget
from app.ui.widgets.crosshair_renderer import CrosshairRenderer
from app.ui.widgets.collapsible_box import CollapsibleBox

if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet

_SettingValue = int | float | bool
PixelMapT = list[list[dict[str, int | bool]]]

SETTING_NAMES: list[str] = [
    "cl_crosshairgap",
    "cl_crosshair_outlinethickness",
    "cl_crosshaircolor_r",
    "cl_crosshaircolor_g",
    "cl_crosshaircolor_b",
    "cl_crosshairalpha",
    "cl_crosshair_dynamic_splitdist",
    "cl_crosshair_recoil",
    "cl_fixedcrosshairgap",
    "cl_crosshaircolor",
    "cl_crosshair_drawoutline",
    "cl_crosshair_dynamic_splitalpha_innermod",
    "cl_crosshair_dynamic_splitalpha_outermod",
    "cl_crosshair_dynamic_maxdist_splitratio",
    "cl_crosshairthickness",
    "cl_crosshairstyle",
    "cl_crosshairdot",
    "cl_crosshairgap_useweaponvalue",
    "cl_crosshairusealpha",
    "cl_crosshair_t",
    "cl_crosshairsize",
]

_CODE_PATTERN: re.Pattern[str] = re.compile(
    r"^CSGO(-[ABCDEFGHJKLMNOPQRSTUVWXYZabcdefhijkmnopqrstuvwxyz23456789]{5}){5}$",
)


class PixelTriggerTab(BaseTab):
    """Pixel Trigger tab with crosshair visualizer, pixel selection, and settings."""

    config_changed = Signal(str, dict)  # component_name, config

    def __init__(self, device_service: DeviceService, parent=None) -> None:
        super().__init__(parent)
        self._device_service = device_service

        self._codec = CS2CrosshairCodec()
        self._renderer = CrosshairRenderer()

        self._settings: dict[str, _SettingValue] = dict(
            CS2CrosshairCodec.DEFAULT_SETTINGS,
        )
        self._settings_controls: dict[str, QtWidgets.QWidget] = {}
        self._updating_controls = False
        self._current_pixel_map: PixelMapT = []
        self._stored_monitor_pixel: tuple[int, int] | None = None

        # Scope crosshair state
        self._scope_width = 1
        self._current_scope_pixel_map: PixelMapT = []
        self._stored_scope_monitor_pixel: tuple[int, int] | None = None
        self._zoom_value = 16

        # ── build UI ────────────────────────────────────────────────────
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        content = QtWidgets.QWidget()
        columns = QtWidgets.QHBoxLayout(content)
        columns.setContentsMargins(8, 8, 8, 8)
        columns.setSpacing(12)

        # ── Left column: Base Settings ──────────────────────────────────
        left_wrapper = QtWidgets.QVBoxLayout()
        left_group = QtWidgets.QGroupBox("Base Settings")
        left_layout = QtWidgets.QVBoxLayout(left_group)
        left_layout.setSpacing(8)

        self._runtime_status_label = QtWidgets.QLabel("Runtime: idle")
        self._runtime_status_label.setWordWrap(True)
        self._runtime_status_label.setStyleSheet(
            "font-weight: bold; color: #555; padding: 2px 0;",
        )
        left_layout.addWidget(self._runtime_status_label)

        self._scoped_label = QtWidgets.QLabel("Scoped: —")
        self._scoped_label.setStyleSheet("color: #555; padding: 2px 0;")
        left_layout.addWidget(self._scoped_label)

        self._enabled_cb = QtWidgets.QCheckBox("Enabled")
        self._enabled_cb.toggled.connect(self._on_component_setting_changed)
        left_layout.addWidget(self._enabled_cb)

        hold_row = QtWidgets.QFormLayout()
        hold_row.setHorizontalSpacing(8)
        hold_row.setVerticalSpacing(4)
        self._hold_key = QtWidgets.QLineEdit()
        self._hold_key.setPlaceholderText("e.g. shift, mouse5")
        self._hold_key.editingFinished.connect(self._on_component_setting_changed)
        hold_row.addRow("Hold key", self._hold_key)
        left_layout.addLayout(hold_row)

        comp_advanced = CollapsibleBox("Advanced")
        self._build_component_settings(comp_advanced.content_layout)
        left_layout.addWidget(comp_advanced)

        left_wrapper.addWidget(left_group)
        left_wrapper.addStretch(1)
        columns.addLayout(left_wrapper, 1)

        # ── Right column: Pixel Selection ───────────────────────────────
        right_wrapper = QtWidgets.QVBoxLayout()
        right_group = QtWidgets.QGroupBox("Pixel Selection")
        right_layout = QtWidgets.QVBoxLayout(right_group)
        right_layout.setSpacing(6)

        self._build_toolbar(right_layout)
        self._build_grid(right_layout)

        self._pixel_info_label = QtWidgets.QLabel("No pixel selected")
        self._pixel_info_label.setWordWrap(True)
        self._pixel_info_label.setStyleSheet("color: #444; font-size: 11px;")
        right_layout.addWidget(self._pixel_info_label)

        self._screen_coord_label = QtWidgets.QLabel("")
        self._screen_coord_label.setStyleSheet("color: #666; font-size: 11px;")
        right_layout.addWidget(self._screen_coord_label)

        # ── Sniper Scope section ──────────────────────────────────────────
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setFrameShadow(QtWidgets.QFrame.Sunken)
        sep.setStyleSheet("color: #ccc;")
        right_layout.addWidget(sep)

        self._build_scope_grid(right_layout)

        self._build_resolution_panel(right_layout)

        ch_advanced = CollapsibleBox("Advanced")
        self._build_crosshair_settings(ch_advanced.content_layout)
        right_layout.addWidget(ch_advanced)

        right_wrapper.addWidget(right_group)
        right_wrapper.addStretch(1)
        columns.addLayout(right_wrapper, 2)

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        self._render_and_display()

    # ── UI builders ─────────────────────────────────────────────────────

    def _build_toolbar(self, parent_layout: QtWidgets.QVBoxLayout) -> None:
        code_row = QtWidgets.QHBoxLayout()
        self._code_input = QtWidgets.QLineEdit()
        self._code_input.setPlaceholderText("CSGO-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX")
        self._code_input.returnPressed.connect(self._parse_code)
        code_row.addWidget(QtWidgets.QLabel("Crosshair Code:"))
        code_row.addWidget(self._code_input, 1)

        parse_btn = QtWidgets.QPushButton("Parse")
        parse_btn.clicked.connect(self._parse_code)
        code_row.addWidget(parse_btn)

        copy_btn = QtWidgets.QPushButton("Copy")
        copy_btn.clicked.connect(self._copy_code)
        code_row.addWidget(copy_btn)

        parent_layout.addLayout(code_row)

        action_row = QtWidgets.QHBoxLayout()
        select_empty_btn = QtWidgets.QPushButton("Select Closest Empty")
        select_empty_btn.setToolTip(
            "Select the empty pixel with alpha 0 that is closest to the geometric centre.",
        )
        select_empty_btn.clicked.connect(self._select_closest_empty_pixel)
        action_row.addWidget(select_empty_btn)

        action_row.addStretch(1)

        self._zoom_label = QtWidgets.QLabel("Zoom: 16")
        action_row.addWidget(self._zoom_label)

        zoom_in_btn = QtWidgets.QPushButton("+")
        zoom_in_btn.setFixedWidth(28)
        zoom_in_btn.clicked.connect(self._zoom_in)
        action_row.addWidget(zoom_in_btn)

        zoom_out_btn = QtWidgets.QPushButton("\u2212")
        zoom_out_btn.setFixedWidth(28)
        zoom_out_btn.clicked.connect(self._zoom_out)
        action_row.addWidget(zoom_out_btn)

        parent_layout.addLayout(action_row)

    def _build_grid(self, parent_layout: QtWidgets.QVBoxLayout) -> None:
        base_header = QtWidgets.QLabel("Base Crosshair")
        base_header.setStyleSheet("font-weight: bold; color: #444; padding-top: 2px;")
        parent_layout.addWidget(base_header)

        hint = QtWidgets.QLabel(
            "Choose a pixel to be monitored for color change — "
            "Should not be covered by your crosshair of course",
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 11px; padding-bottom: 2px;")
        parent_layout.addWidget(hint)

        self._grid = PixelGridWidget()
        self._grid.pixel_selected.connect(self._on_pixel_selected)
        self._grid.selection_changed.connect(self._on_selection_changed)

        self._scroll_area = QtWidgets.QScrollArea()
        self._scroll_area.setWidgetResizable(False)
        self._scroll_area.setWidget(self._grid)
        self._scroll_area.setFrameShape(QtWidgets.QScrollArea.Shape.StyledPanel)
        self._scroll_area.setMinimumHeight(200)
        self._scroll_area.setMaximumHeight(560)
        parent_layout.addWidget(self._scroll_area, 1)

    def _build_scope_grid(self, parent_layout: QtWidgets.QVBoxLayout) -> None:
        scope_header = QtWidgets.QLabel("Sniper Scope Crosshair")
        scope_header.setStyleSheet("font-weight: bold; color: #444; padding-top: 2px;")
        parent_layout.addWidget(scope_header)

        width_row = QtWidgets.QHBoxLayout()
        width_row.addWidget(QtWidgets.QLabel("Scope width:"))
        self._scope_width_spin = QtWidgets.QSpinBox()
        self._scope_width_spin.setRange(1, 6)
        self._scope_width_spin.setValue(1)
        self._scope_width_spin.valueChanged.connect(self._on_scope_width_changed)
        width_row.addWidget(self._scope_width_spin)
        width_row.addStretch()
        parent_layout.addLayout(width_row)

        scope_hint = QtWidgets.QLabel(
            "Select a pixel to monitor while scoped. "
            "Pick one not covered by the black scope crosshair.",
        )
        scope_hint.setWordWrap(True)
        scope_hint.setStyleSheet("color: #666; font-size: 11px; padding-bottom: 2px;")
        parent_layout.addWidget(scope_hint)

        self._scope_grid = PixelGridWidget()
        self._scope_grid.pixel_selected.connect(self._on_scope_pixel_selected)
        self._scope_grid.selection_changed.connect(self._on_scope_selection_changed)

        self._scope_scroll_area = QtWidgets.QScrollArea()
        self._scope_scroll_area.setWidgetResizable(False)
        self._scope_scroll_area.setWidget(self._scope_grid)
        self._scope_scroll_area.setFrameShape(QtWidgets.QScrollArea.Shape.StyledPanel)
        self._scope_scroll_area.setMinimumHeight(200)
        self._scope_scroll_area.setMaximumHeight(560)
        parent_layout.addWidget(self._scope_scroll_area, 1)

        self._scope_pixel_info_label = QtWidgets.QLabel("No scope pixel selected")
        self._scope_pixel_info_label.setWordWrap(True)
        self._scope_pixel_info_label.setStyleSheet("color: #444; font-size: 11px;")
        parent_layout.addWidget(self._scope_pixel_info_label)

        self._scope_screen_coord_label = QtWidgets.QLabel("")
        self._scope_screen_coord_label.setStyleSheet("color: #666; font-size: 11px;")
        parent_layout.addWidget(self._scope_screen_coord_label)

    def _build_resolution_panel(self, parent_layout: QtWidgets.QVBoxLayout) -> None:
        game_row = QtWidgets.QHBoxLayout()
        game_row.addWidget(QtWidgets.QLabel("Game Resolution:"))
        self._res_w = QtWidgets.QSpinBox()
        self._res_w.setRange(640, 7680)
        self._res_w.setValue(1920)
        self._res_w.setSingleStep(10)
        self._res_w.valueChanged.connect(self._on_resolution_changed)
        game_row.addWidget(self._res_w)
        game_row.addWidget(QtWidgets.QLabel("\u00d7"))
        self._res_h = QtWidgets.QSpinBox()
        self._res_h.setRange(480, 4320)
        self._res_h.setValue(1080)
        self._res_h.setSingleStep(10)
        self._res_h.valueChanged.connect(self._on_resolution_changed)
        game_row.addWidget(self._res_h)

        game_row.addSpacing(12)
        self._stretch_checkbox = QtWidgets.QCheckBox("Stretched")
        self._stretch_checkbox.setToolTip(
            "Stretches the game framebuffer to the display resolution "
            "using linear filtering (display-like). Unchecked shows native 1:1 pixels.",
        )
        self._stretch_checkbox.toggled.connect(self._render_and_display)
        game_row.addWidget(self._stretch_checkbox)
        game_row.addStretch()
        parent_layout.addLayout(game_row)

        display_row = QtWidgets.QHBoxLayout()
        display_row.addWidget(QtWidgets.QLabel("Display Resolution:"))
        self._display_w = QtWidgets.QSpinBox()
        self._display_w.setRange(640, 7680)
        self._display_w.setValue(1920)
        self._display_w.setSingleStep(10)
        self._display_w.valueChanged.connect(self._on_resolution_changed)
        display_row.addWidget(self._display_w)
        display_row.addWidget(QtWidgets.QLabel("\u00d7"))
        self._display_h = QtWidgets.QSpinBox()
        self._display_h.setRange(480, 4320)
        self._display_h.setValue(1080)
        self._display_h.setSingleStep(10)
        self._display_h.valueChanged.connect(self._on_resolution_changed)
        display_row.addWidget(self._display_h)
        display_row.addStretch()
        parent_layout.addLayout(display_row)

    def _build_component_settings(self, parent_layout: QtWidgets.QVBoxLayout) -> None:
        form = QtWidgets.QFormLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(4)

        self._threshold = QtWidgets.QDoubleSpinBox()
        self._threshold.setRange(0.0, 500.0)
        self._threshold.setDecimals(1)
        self._threshold.setSingleStep(0.1)
        self._threshold.setValue(35.0)
        self._threshold.valueChanged.connect(self._on_component_setting_changed)
        form.addRow("Threshold", self._threshold)

        self._click_delay = QtWidgets.QDoubleSpinBox()
        self._click_delay.setRange(0.0, 5.0)
        self._click_delay.setDecimals(4)
        self._click_delay.setSingleStep(0.001)
        self._click_delay.setValue(0.05)
        self._click_delay.valueChanged.connect(self._on_component_setting_changed)
        form.addRow("Click delay (s)", self._click_delay)

        self._cooldown = QtWidgets.QDoubleSpinBox()
        self._cooldown.setRange(0.0, 5.0)
        self._cooldown.setDecimals(4)
        self._cooldown.setSingleStep(0.001)
        self._cooldown.setValue(0.15)
        self._cooldown.valueChanged.connect(self._on_component_setting_changed)
        form.addRow("Cooldown (s)", self._cooldown)

        self._poll_interval = QtWidgets.QDoubleSpinBox()
        self._poll_interval.setRange(0.0001, 1.0)
        self._poll_interval.setDecimals(4)
        self._poll_interval.setSingleStep(0.0005)
        self._poll_interval.setValue(0.001)
        self._poll_interval.valueChanged.connect(self._on_component_setting_changed)
        form.addRow("Poll interval (s)", self._poll_interval)

        self._monitor_index = QtWidgets.QSpinBox()
        self._monitor_index.setRange(1, 16)
        self._monitor_index.setValue(1)
        self._monitor_index.valueChanged.connect(self._on_component_setting_changed)
        form.addRow("Monitor index", self._monitor_index)

        self._scope_blur_offset_x = QtWidgets.QSpinBox()
        self._scope_blur_offset_x.setRange(-500, 500)
        self._scope_blur_offset_x.setValue(0)
        self._scope_blur_offset_x.setToolTip(
            "Temporary horizontal pixel offset applied when scope-in blur is detected.",
        )
        self._scope_blur_offset_x.valueChanged.connect(self._on_component_setting_changed)
        form.addRow("Scope blur offset X", self._scope_blur_offset_x)

        self._scope_blur_offset_y = QtWidgets.QSpinBox()
        self._scope_blur_offset_y.setRange(-500, 500)
        self._scope_blur_offset_y.setValue(0)
        self._scope_blur_offset_y.setToolTip(
            "Temporary vertical pixel offset applied when scope-in blur is detected.",
        )
        self._scope_blur_offset_y.valueChanged.connect(self._on_component_setting_changed)
        form.addRow("Scope blur offset Y", self._scope_blur_offset_y)

        self._scope_blur_duration_ms = QtWidgets.QSpinBox()
        self._scope_blur_duration_ms.setRange(0, 5000)
        self._scope_blur_duration_ms.setSingleStep(25)
        self._scope_blur_duration_ms.setValue(0)
        self._scope_blur_duration_ms.setToolTip(
            "How long to use the blur offset after scope detection turns true. Set 0 to disable.",
        )
        self._scope_blur_duration_ms.valueChanged.connect(self._on_component_setting_changed)
        form.addRow("Scope blur duration (ms)", self._scope_blur_duration_ms)

        parent_layout.addLayout(form)

    def _build_crosshair_settings(self, parent_layout: QtWidgets.QVBoxLayout) -> None:
        crosshair_group = QtWidgets.QGroupBox("Crosshair Settings")
        crosshair_layout = QtWidgets.QVBoxLayout(crosshair_group)
        crosshair_layout.setSpacing(4)

        columns_2 = QtWidgets.QHBoxLayout()
        columns_2.setSpacing(12)

        # ── Left column: numeric controls ───────────────────────────────
        left_form = QtWidgets.QFormLayout()
        left_form.setHorizontalSpacing(6)
        left_form.setVerticalSpacing(4)

        float_controls: list[tuple[str, float, float, float, str]] = [
            ("cl_crosshairsize", 0.0, 20.0, 0.1, "Size"),
            ("cl_crosshairgap", -10.0, 10.0, 0.1, "Gap"),
            ("cl_crosshairthickness", 0.0, 10.0, 0.1, "Thickness"),
            ("cl_crosshair_outlinethickness", 0.0, 5.0, 0.5, "Outline Thk"),
        ]
        for key, low, high, step, label in float_controls:
            spin = QtWidgets.QDoubleSpinBox()
            spin.setRange(low, high)
            spin.setSingleStep(step)
            spin.setDecimals(2)
            spin.valueChanged.connect(
                lambda _v, setting_key=key: self._on_setting_changed(setting_key),
            )
            self._settings_controls[key] = spin
            left_form.addRow(f"{label}:", spin)

        int_controls: list[tuple[str, int, int, str]] = [
            ("cl_crosshairalpha", 0, 255, "Alpha"),
            ("cl_crosshaircolor_r", 0, 255, "Red"),
            ("cl_crosshaircolor_g", 0, 255, "Green"),
            ("cl_crosshaircolor_b", 0, 255, "Blue"),
        ]
        for key, low, high, label in int_controls:
            spin = QtWidgets.QSpinBox()
            spin.setRange(low, high)
            spin.valueChanged.connect(
                lambda _v, setting_key=key: self._on_setting_changed(setting_key),
            )
            self._settings_controls[key] = spin
            left_form.addRow(f"{label}:", spin)

        columns_2.addLayout(left_form, 1)

        # ── Right column: combos + checkboxes ───────────────────────────
        right_form = QtWidgets.QFormLayout()
        right_form.setHorizontalSpacing(6)
        right_form.setVerticalSpacing(4)

        style_combo = QtWidgets.QComboBox()
        style_labels = [
            "0 (Default)", "1 (Default)", "2 (Classic)",
            "3 (Classic Dynamic)", "4 (Classic Static)", "5 (Classic Static)",
        ]
        for idx, label in enumerate(style_labels):
            style_combo.addItem(label, idx)
        style_combo.currentIndexChanged.connect(
            lambda _i: self._on_setting_changed("cl_crosshairstyle"),
        )
        self._settings_controls["cl_crosshairstyle"] = style_combo
        right_form.addRow("Style:", style_combo)

        color_combo = QtWidgets.QComboBox()
        color_options = [
            "0 (Red)", "1 (Green)", "2 (Yellow)",
            "3 (Blue)", "4 (Cyan)", "5 (Custom RGB)",
        ]
        for idx, label in enumerate(color_options):
            color_combo.addItem(label, idx)
        color_combo.currentIndexChanged.connect(
            lambda _i: self._on_setting_changed("cl_crosshaircolor"),
        )
        self._settings_controls["cl_crosshaircolor"] = color_combo
        right_form.addRow("Color:", color_combo)

        columns_2.addLayout(right_form, 1)
        crosshair_layout.addLayout(columns_2)

        # ── Checkboxes row (full width below the two columns) ───────────
        checkboxes: list[tuple[str, str]] = [
            ("cl_crosshair_drawoutline", "Draw Outline"),
            ("cl_crosshairdot", "Center Dot"),
            ("cl_crosshair_t", "T-Style (no top)"),
            ("cl_crosshairusealpha", "Use Alpha"),
            ("cl_crosshair_recoil", "Recoil Follow"),
            ("cl_crosshairgap_useweaponvalue", "Use Weapon Gap"),
        ]
        cb_row = QtWidgets.QHBoxLayout()
        cb_row.setSpacing(10)
        for key, label in checkboxes:
            checkbox = QtWidgets.QCheckBox(label)
            checkbox.toggled.connect(
                lambda _checked, setting_key=key: self._on_setting_changed(setting_key),
            )
            self._settings_controls[key] = checkbox
            cb_row.addWidget(checkbox)
        cb_row.addStretch()
        crosshair_layout.addLayout(cb_row)

        parent_layout.addWidget(crosshair_group)

    # ── crosshair actions ───────────────────────────────────────────────

    def _on_resolution_changed(self, _value: int = 0) -> None:
        self._render_and_display()
        self._select_closest_empty_scope_pixel()

    def _parse_code(self) -> None:
        code = self._code_input.text().strip()
        if not code:
            self._flash_message("Enter a crosshair code first")
            return

        normalized = code
        if not normalized.startswith("CSGO-"):
            raw = normalized.replace("-", "")
            if len(raw) == 25:
                normalized = "CSGO-{}-{}-{}-{}-{}".format(
                    raw[:5], raw[5:10], raw[10:15], raw[15:20], raw[20:],
                )

        if _CODE_PATTERN.fullmatch(normalized) is None:
            self._flash_message("Invalid crosshair code format")
            return

        parsed = self._codec.parse_code(normalized)
        self._settings = dict(parsed)
        self._sync_controls_from_settings()
        self._render_and_display()
        # Auto-select the closest empty pixel for the new crosshair
        self._select_closest_empty_pixel()
        self._flash_message("Crosshair loaded")
        self._emit_config_changed()

    def _copy_code(self) -> None:
        code = self._codec.generate_code(self._settings)
        QtWidgets.QApplication.clipboard().setText(code)
        self._flash_message("Code copied to clipboard")

    def _zoom_in(self) -> None:
        self._zoom_value = min(50, self._zoom_value + 2)
        self._grid.set_zoom(self._zoom_value)
        self._scope_grid.set_zoom(self._zoom_value)
        self._zoom_label.setText(f"Zoom: {self._zoom_value}")
        QTimer.singleShot(0, self._center_scroll)
        QTimer.singleShot(0, self._center_scope_scroll)

    def _zoom_out(self) -> None:
        self._zoom_value = max(2, self._zoom_value - 2)
        self._grid.set_zoom(self._zoom_value)
        self._scope_grid.set_zoom(self._zoom_value)
        self._zoom_label.setText(f"Zoom: {self._zoom_value}")
        QTimer.singleShot(0, self._center_scroll)
        QTimer.singleShot(0, self._center_scope_scroll)

    def _select_closest_empty_pixel(self) -> None:
        pixel = self._grid.find_closest_fully_empty_pixel()
        if pixel is None:
            self._flash_message("No completely empty pixel was found")
            return
        x, y = pixel
        if self._grid.select_single_pixel(x, y):
            self._flash_message("Closest completely empty pixel selected")
            QTimer.singleShot(0, self._center_scroll)
            self._emit_config_changed()

    def _render_and_display(self, _value: int | float | bool = 0) -> None:
        screen_width = self._res_w.value()
        screen_height = self._res_h.value()
        stretch_enabled = self._stretch_checkbox.isChecked()

        stretch_kw: dict[str, Any] = (
            {
                "stretch_to_display": True,
                "display_width": self._display_w.value(),
                "display_height": self._display_h.value(),
                "stretch_filter": "linear",
            }
            if stretch_enabled
            else {"stretch_to_display": False}
        )

        pixel_map = self._renderer.render_pixel_map_for_resolution(
            self._settings, screen_width, screen_height, **stretch_kw,
        )
        self._current_pixel_map = pixel_map
        self._grid.set_pixel_map(pixel_map)
        self._grid.set_zoom(self._zoom_value)

        scope_pixel_map = self._renderer.render_scope_pixel_map(
            self._scope_width_spin.value(),
            screen_width, screen_height,
            **stretch_kw,
        )
        self._current_scope_pixel_map = scope_pixel_map
        self._scope_grid.set_pixel_map(scope_pixel_map)
        self._scope_grid.set_zoom(self._zoom_value)

        self._zoom_label.setText(f"Zoom: {self._zoom_value}")
        self._code_input.setText(self._codec.generate_code(self._settings))
        self._update_selection_status()
        self._update_scope_selection_status()
        QTimer.singleShot(0, self._center_scroll)
        QTimer.singleShot(0, self._center_scope_scroll)

    def _center_scroll(self) -> None:
        content_size = self._grid.sizeHint()
        viewport_size = self._scroll_area.viewport().size()
        hbar = self._scroll_area.horizontalScrollBar()
        vbar = self._scroll_area.verticalScrollBar()
        hbar.setValue(max(0, (content_size.width() - viewport_size.width()) // 2))
        vbar.setValue(max(0, (content_size.height() - viewport_size.height()) // 2))

    def _center_scope_scroll(self) -> None:
        content_size = self._scope_grid.sizeHint()
        viewport_size = self._scope_scroll_area.viewport().size()
        hbar = self._scope_scroll_area.horizontalScrollBar()
        vbar = self._scope_scroll_area.verticalScrollBar()
        hbar.setValue(max(0, (content_size.width() - viewport_size.width()) // 2))
        vbar.setValue(max(0, (content_size.height() - viewport_size.height()) // 2))

    # ── scope crosshair handlers ─────────────────────────────────────────

    def _on_scope_width_changed(self) -> None:
        self._scope_width = self._scope_width_spin.value()
        self._render_and_display()
        self._select_closest_empty_scope_pixel()
        self._emit_config_changed()

    def _on_scope_pixel_selected(self, _x: int, _y: int) -> None:
        self._update_scope_selection_status()
        self._emit_config_changed()

    def _on_scope_selection_changed(
        self, _selected: AbstractSet[tuple[int, int]],
    ) -> None:
        self._update_scope_selection_status()
        self._emit_config_changed()

    def _select_closest_empty_scope_pixel(self) -> None:
        pixel = self._scope_grid.find_closest_fully_empty_pixel()
        if pixel is None:
            return
        x, y = pixel
        self._scope_grid.select_single_pixel(x, y)
        self._update_scope_selection_status()

    def _update_scope_selection_status(self) -> None:
        selected = self._scope_grid.get_selected_pixels()
        if not selected:
            self._scope_pixel_info_label.setText("No scope pixel selected")
            self._scope_screen_coord_label.setText("")
            return

        info = self._scope_grid.selected_pixel_info()
        if not info:
            self._scope_pixel_info_label.setText("No scope pixel selected")
            self._scope_screen_coord_label.setText("")
            return

        pixel = info[-1]
        x_text = self._format_coordinate(pixel["x"])
        y_text = self._format_coordinate(pixel["y"])
        self._scope_pixel_info_label.setText(
            f"Pixel ({x_text}, {y_text})  |  "
            f"RGBA({pixel['r']}, {pixel['g']}, {pixel['b']}, {pixel['a']})  |  "
            f"Crosshair: {'Yes' if pixel['is_crosshair'] else 'No'}",
        )

        if len(selected) == 1:
            sx, sy = next(iter(selected))
            screen_pos = self._scope_screen_pixel_coordinates(sx, sy)
            if screen_pos is not None:
                self._scope_screen_coord_label.setText(
                    f"Display pixel: ({screen_pos[0]}, {screen_pos[1]})",
                )
            else:
                self._scope_screen_coord_label.setText("")
        else:
            self._scope_screen_coord_label.setText("")

    def _scope_screen_pixel_coordinates(
        self, pixel_x: int, pixel_y: int,
    ) -> tuple[int, int] | None:
        preview_height = len(self._current_scope_pixel_map)
        preview_width = (
            len(self._current_scope_pixel_map[0])
            if self._current_scope_pixel_map else 0
        )
        if preview_width <= 0 or preview_height <= 0:
            return None

        frame_width, frame_height = self._target_frame_dimensions()
        origin_x = (frame_width - preview_width) / 2.0
        origin_y = (frame_height - preview_height) / 2.0

        screen_x = origin_x + pixel_x
        screen_y = origin_y + pixel_y
        if not math.isclose(screen_x, round(screen_x), abs_tol=1e-9):
            screen_x = round(screen_x)
        if not math.isclose(screen_y, round(screen_y), abs_tol=1e-9):
            screen_y = round(screen_y)
        return int(screen_x), int(screen_y)

    def get_selected_scope_monitor_pixel(self) -> tuple[int, int] | None:
        """Return the selected scope pixel in framebuffer coordinates."""
        selected = self._scope_grid.get_selected_pixels()
        if not selected:
            return None
        sx, sy = next(iter(selected))
        return self._scope_screen_pixel_coordinates(sx, sy)

    def _restore_scope_pixel_selection(self, fb_x: int, fb_y: int) -> None:
        preview_height = len(self._current_scope_pixel_map)
        preview_width = (
            len(self._current_scope_pixel_map[0])
            if self._current_scope_pixel_map else 0
        )
        if preview_width <= 0 or preview_height <= 0:
            return

        frame_width, frame_height = self._target_frame_dimensions()
        origin_x = (frame_width - preview_width) / 2.0
        origin_y = (frame_height - preview_height) / 2.0
        px = int(fb_x - origin_x)
        py = int(fb_y - origin_y)
        self._scope_grid.select_single_pixel(px, py)
        self._update_scope_selection_status()

    # ── settings sync ───────────────────────────────────────────────────

    def _on_setting_changed(self, key: str) -> None:
        if self._updating_controls:
            return
        self._settings[key] = self._read_control(key)
        self._render_and_display()

    def _on_component_setting_changed(self) -> None:
        self._emit_config_changed()

    def _read_control(self, key: str) -> _SettingValue:
        control = self._settings_controls[key]
        if isinstance(control, QtWidgets.QDoubleSpinBox):
            return control.value()
        if isinstance(control, QtWidgets.QSpinBox):
            return control.value()
        if isinstance(control, QtWidgets.QComboBox):
            return int(control.currentData())
        if isinstance(control, QtWidgets.QCheckBox):
            return control.isChecked()
        raise TypeError(f"unknown control type for {key}: {type(control).__name__}")

    def _set_control_value(self, key: str, value: _SettingValue) -> None:
        control = self._settings_controls[key]
        if isinstance(control, QtWidgets.QDoubleSpinBox):
            control.setValue(float(value))
        elif isinstance(control, QtWidgets.QSpinBox):
            control.setValue(int(value))
        elif isinstance(control, QtWidgets.QComboBox):
            index = control.findData(int(value))
            if index >= 0:
                control.setCurrentIndex(index)
        elif isinstance(control, QtWidgets.QCheckBox):
            control.setChecked(bool(value))

    def _sync_controls_from_settings(self) -> None:
        self._updating_controls = True
        try:
            for key in SETTING_NAMES:
                if key in self._settings_controls and key in self._settings:
                    self._set_control_value(key, self._settings[key])
        finally:
            self._updating_controls = False

    # ── pixel selection signals ─────────────────────────────────────────

    def _on_pixel_selected(self, _x: int, _y: int) -> None:
        self._update_selection_status()
        self._emit_config_changed()

    def _on_selection_changed(self, selected: AbstractSet[tuple[int, int]]) -> None:
        self._update_selection_status()
        self._emit_config_changed()

    def _flash_message(self, message: str, duration_ms: int = 2500) -> None:
        """Show a temporary message in the pixel info label area."""
        self._pixel_info_label.setText(message)
        QTimer.singleShot(duration_ms, self._update_selection_status)

    def _update_selection_status(self) -> None:
        selected = self._grid.get_selected_pixels()
        if not selected:
            self._pixel_info_label.setText("No pixel selected")
            self._screen_coord_label.setText("")
            return

        info = self._grid.selected_pixel_info()
        if not info:
            self._pixel_info_label.setText("No pixel selected")
            self._screen_coord_label.setText("")
            return

        pixel = info[-1]
        x_text = self._format_coordinate(pixel["x"])
        y_text = self._format_coordinate(pixel["y"])
        self._pixel_info_label.setText(
            f"Pixel ({x_text}, {y_text})  |  "
            f"RGBA({pixel['r']}, {pixel['g']}, {pixel['b']}, {pixel['a']})  |  "
            f"Crosshair: {'Yes' if pixel['is_crosshair'] else 'No'}",
        )

        if len(selected) == 1:
            sx, sy = next(iter(selected))
            screen_pos = self._screen_pixel_coordinates(sx, sy)
            if screen_pos is not None:
                self._screen_coord_label.setText(
                    f"Display pixel: ({screen_pos[0]}, {screen_pos[1]})",
                )
            else:
                self._screen_coord_label.setText("")
        else:
            self._screen_coord_label.setText("")

    def _screen_pixel_coordinates(self, pixel_x: int, pixel_y: int) -> tuple[int, int] | None:
        preview_height = len(self._current_pixel_map)
        preview_width = len(self._current_pixel_map[0]) if self._current_pixel_map else 0
        if preview_width <= 0 or preview_height <= 0:
            return None

        frame_width, frame_height = self._target_frame_dimensions()
        origin_x = (frame_width - preview_width) / 2.0
        origin_y = (frame_height - preview_height) / 2.0

        screen_x = origin_x + pixel_x
        screen_y = origin_y + pixel_y

        if not math.isclose(screen_x, round(screen_x), abs_tol=1e-9):
            screen_x = round(screen_x)
        if not math.isclose(screen_y, round(screen_y), abs_tol=1e-9):
            screen_y = round(screen_y)

        return int(screen_x), int(screen_y)

    def _target_frame_dimensions(self) -> tuple[int, int]:
        if self._stretch_checkbox.isChecked():
            return self._display_w.value(), self._display_h.value()
        return self._res_w.value(), self._res_h.value()

    @staticmethod
    def _format_coordinate(value: int | float | bool) -> str:
        numeric = float(value)
        if math.isclose(numeric, round(numeric), abs_tol=1e-9):
            return str(int(round(numeric)))
        return f"{numeric:.1f}"

    def get_selected_monitor_pixel(self) -> tuple[int, int] | None:
        """Return the selected pixel in framebuffer coordinates, or None."""
        selected = self._grid.get_selected_pixels()
        if not selected:
            return None
        sx, sy = next(iter(selected))
        return self._screen_pixel_coordinates(sx, sy)

    # ── BaseTab interface ───────────────────────────────────────────────

    def load_config(self, config: dict[str, Any]) -> None:
        crosshair_code = config.get("crosshair_code", "")
        if crosshair_code:
            self._code_input.setText(crosshair_code)
            parsed = self._codec.parse_code(crosshair_code)
            if parsed != self._codec.DEFAULT_SETTINGS:
                self._settings = dict(parsed)
                self._sync_controls_from_settings()

        game_res = config.get("game_resolution", {"width": 1920, "height": 1080})
        if isinstance(game_res, dict):
            self._res_w.setValue(max(640, int(game_res.get("width", 1920))))
            self._res_h.setValue(max(480, int(game_res.get("height", 1080))))

        display_res = config.get("display_resolution", {"width": 1920, "height": 1080})
        if isinstance(display_res, dict):
            self._display_w.setValue(max(640, int(display_res.get("width", 1920))))
            self._display_h.setValue(max(480, int(display_res.get("height", 1080))))

        self._stretch_checkbox.setChecked(bool(config.get("stretched", True)))

        self._enabled_cb.setChecked(bool(config.get("enabled", False)))
        self._hold_key.setText(str(config.get("hold_key_name", "shift")))
        self._threshold.setValue(float(config.get("threshold", 35.0)))
        self._click_delay.setValue(float(config.get("click_delay", 0.05)))
        self._cooldown.setValue(float(config.get("cooldown", 0.15)))
        self._poll_interval.setValue(float(config.get("poll_interval", 0.001)))
        self._monitor_index.setValue(int(config.get("monitor_index", 1)))
        self._scope_blur_offset_x.setValue(int(config.get("scope_blur_offset_x", 0)))
        self._scope_blur_offset_y.setValue(int(config.get("scope_blur_offset_y", 0)))
        self._scope_blur_duration_ms.setValue(
            max(0, int(config.get("scope_blur_duration_ms", 0))),
        )

        self._render_and_display()

        monitor_px = config.get("monitor_pixel_x")
        monitor_py = config.get("monitor_pixel_y")
        if monitor_px is not None and monitor_py is not None:
            self._stored_monitor_pixel = (int(monitor_px), int(monitor_py))
            self._restore_pixel_selection(int(monitor_px), int(monitor_py))
        else:
            self._stored_monitor_pixel = None
            self._select_closest_empty_pixel()

        # Scope fields
        scope_w = config.get("scope_width", 1)
        self._scope_width_spin.setValue(max(1, min(6, int(scope_w))))

        scope_px = config.get("scope_monitor_pixel_x")
        scope_py = config.get("scope_monitor_pixel_y")
        if scope_px is not None and scope_py is not None:
            self._stored_scope_monitor_pixel = (int(scope_px), int(scope_py))
            self._restore_scope_pixel_selection(int(scope_px), int(scope_py))
        else:
            self._stored_scope_monitor_pixel = None
            self._select_closest_empty_scope_pixel()

    def _restore_pixel_selection(self, fb_x: int, fb_y: int) -> None:
        preview_height = len(self._current_pixel_map)
        preview_width = len(self._current_pixel_map[0]) if self._current_pixel_map else 0
        if preview_width <= 0 or preview_height <= 0:
            return

        frame_width, frame_height = self._target_frame_dimensions()
        origin_x = (frame_width - preview_width) / 2.0
        origin_y = (frame_height - preview_height) / 2.0
        px = int(fb_x - origin_x)
        py = int(fb_y - origin_y)
        self._grid.select_single_pixel(px, py)
        self._update_selection_status()

    def extract_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {
            "enabled": self._enabled_cb.isChecked(),
            "hold_key_name": self._hold_key.text().strip() or "shift",
            "threshold": self._threshold.value(),
            "click_delay": self._click_delay.value(),
            "cooldown": self._cooldown.value(),
            "poll_interval": self._poll_interval.value(),
            "monitor_index": self._monitor_index.value(),
            "crosshair_code": self._codec.generate_code(self._settings),
            "game_resolution": {
                "width": self._res_w.value(),
                "height": self._res_h.value(),
            },
            "display_resolution": {
                "width": self._display_w.value(),
                "height": self._display_h.value(),
            },
            "stretched": self._stretch_checkbox.isChecked(),
            "scope_width": self._scope_width_spin.value(),
            "scope_blur_offset_x": self._scope_blur_offset_x.value(),
            "scope_blur_offset_y": self._scope_blur_offset_y.value(),
            "scope_blur_duration_ms": self._scope_blur_duration_ms.value(),
        }

        monitor_pixel = self.get_selected_monitor_pixel()
        if monitor_pixel is not None:
            config["monitor_pixel_x"] = monitor_pixel[0]
            config["monitor_pixel_y"] = monitor_pixel[1]
        elif self._stored_monitor_pixel is not None:
            config["monitor_pixel_x"] = self._stored_monitor_pixel[0]
            config["monitor_pixel_y"] = self._stored_monitor_pixel[1]
        else:
            config["monitor_pixel_x"] = None
            config["monitor_pixel_y"] = None

        scope_pixel = self.get_selected_scope_monitor_pixel()
        if scope_pixel is not None:
            config["scope_monitor_pixel_x"] = scope_pixel[0]
            config["scope_monitor_pixel_y"] = scope_pixel[1]
        elif self._stored_scope_monitor_pixel is not None:
            config["scope_monitor_pixel_x"] = self._stored_scope_monitor_pixel[0]
            config["scope_monitor_pixel_y"] = self._stored_scope_monitor_pixel[1]
        else:
            config["scope_monitor_pixel_x"] = None
            config["scope_monitor_pixel_y"] = None

        return config

    def refresh_devices(self) -> None:
        pass

    def set_runtime_status(self, message: str) -> None:
        """Update the runtime status label.

        Maps component status messages to a clean "running" / "idle" display.
        """
        msg_lower = message.lower().strip()
        if msg_lower in ("started.", "running"):
            status = "running"
        elif msg_lower in ("stopped.", "stopping.", "idle", ""):
            status = "idle"
        elif "error" in msg_lower or "failed" in msg_lower:
            status = "idle"
        else:
            status = message
        self._runtime_status_label.setText(f"Runtime: {status}")

    def set_scoped_status(self, scoped: bool | None) -> None:
        if scoped is True:
            text = "True"
        elif scoped is False:
            text = "False"
        else:
            text = "—"
        self._scoped_label.setText(f"Scoped: {text}")

    def _emit_config_changed(self) -> None:
        self.config_changed.emit("pixel_trigger", self.extract_config())

    def set_pixel_selection(self, monitor_x: int, monitor_y: int) -> None:
        self._restore_pixel_selection(monitor_x, monitor_y)
