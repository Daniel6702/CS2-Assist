"""Render CS2 crosshairs as pixel-precise maps for the crosshair visualizer."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal, TypedDict

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPainter


SettingsValue = int | float | bool
StretchFilter = Literal["nearest", "linear"]


class PixelCell(TypedDict):
    r: int
    g: int
    b: int
    a: int
    is_crosshair: bool


class ResolvedMetrics(TypedDict):
    length: int
    thickness: int
    gap: int
    outline: int
    canvas_size: int


@dataclass(frozen=True, slots=True)
class _Metrics:
    length: int
    thickness: int
    gap: int
    outline: int
    canvas_size: int
    t_style: bool


@dataclass(frozen=True, slots=True)
class _RectSpec:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class _ArmSpec:
    color: _RectSpec
    outline: _RectSpec | None


PRESET_COLORS: Final[dict[int, tuple[int, int, int]]] = {
    0: (255, 0, 0),
    1: (0, 255, 0),
    2: (255, 255, 0),
    3: (0, 0, 255),
    4: (0, 255, 255),
}


# Empirically measured 1920x1080 setting-to-pixel thresholds.
# Each value applies from its threshold up to the next threshold.
_LENGTH_MAP_1080: Final[tuple[tuple[float, int], ...]] = (
    (0.0, 0),
    (0.3, 1),
    (0.7, 2),
    (1.2, 3),
    (1.6, 4),
    (2.1, 5),
    (2.5, 6),
    (2.9, 7),
    (3.399, 8),
    (3.799, 9),
    (4.299, 10),
    (4.699, 11),
    (5.199, 12),
    (5.599, 13),
    (5.999, 14),
    (6.499, 15),
    (6.899, 16),
    (7.399, 17),
    (7.799, 18),
    (8.299, 19),
    (8.699, 20),
    (9.199, 21),
    (9.599, 22),
    (10.099, 23),
)

_THICKNESS_MAP_1080: Final[tuple[tuple[float, int], ...]] = (
    (0.0, 1),
    (0.7, 2),
    (1.12, 3),
    (1.56, 4),
    (2.01, 5),
    (2.45, 6),
    (2.89, 7),
)

_GAP_MAP_1080: Final[tuple[tuple[float, int], ...]] = (
    (-7.0, -3),
    (-5.9, -2),
    (-4.9, -1),
    (-3.0, 0),
    (-2.0, 1),
    (-1.0, 2),
    (-0.05, 3),
    (1.0, 4),
    (2.0, 5),
    (3.0, 6),
    (4.0, 7),
)


class CrosshairRenderer:
    """Render classic CS2 crosshairs as deterministic pixels.

    Native crosshair geometry is resolved and rasterised before any display
    stretching is applied. The native raster uses a thickness-aware axis:

    * odd thicknesses are centred on a pixel centre;
    * even thicknesses are centred on the boundary between two pixels.

    The generated preview is then tightly cropped to the actual visible
    crosshair, leaving exactly one fully transparent pixel on each side.
    """

    REFERENCE_HEIGHT: Final[int] = 1080
    _TRIM_PADDING: Final[int] = 1

    def render(
        self,
        settings: dict[str, SettingsValue],
        screen_width: int = 1920,
        screen_height: int = 1080,
    ) -> QImage:
        """Render the native game-framebuffer crosshair preview."""
        self._validate_resolution(screen_width, screen_height, "game")

        metrics = self._metrics(settings, screen_height)
        image = QImage(
            metrics.canvas_size,
            metrics.canvas_size,
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(QColor(0, 0, 0, 0))

        style = int(settings["cl_crosshairstyle"])
        if style not in (2, 4):
            return image

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Pixel-centre coordinate of the raster axis, stored in half-pixel
        # units. For a 64-pixel crop, c=32. Odd strokes use axis 32.0;
        # even strokes use axis 31.5, exactly between pixels 31 and 32.
        crop_center = metrics.canvas_size // 2
        axis_twice = (
            crop_center * 2
            if metrics.thickness % 2 != 0
            else (crop_center * 2) - 1
        )

        alpha = self._alpha(settings)
        crosshair_color = QColor(*self._color(settings), alpha)
        outline_color = QColor(0, 0, 0, alpha)

        arms = self._arm_specs(axis_twice, metrics)

        for arm in arms:
            if arm.outline is not None:
                self._fill_rect(painter, arm.outline, outline_color)

        for arm in arms:
            self._fill_rect(painter, arm.color, crosshair_color)

        if bool(settings["cl_crosshairdot"]):
            dot = self._centered_square(axis_twice, metrics.thickness)
            if metrics.outline > 0:
                self._fill_rect(
                    painter,
                    self._expanded(dot, metrics.outline),
                    outline_color,
                )
            self._fill_rect(painter, dot, crosshair_color)

        painter.end()
        return self._trim_to_content(
            image,
            padding=self._TRIM_PADDING,
        )

    def render_for_resolution(
        self,
        settings: dict[str, SettingsValue],
        screen_width: int,
        screen_height: int,
        *,
        stretch_to_display: bool = False,
        display_width: int | None = None,
        display_height: int | None = None,
        stretch_filter: StretchFilter = "linear",
    ) -> QImage:
        """Render a native preview or a framebuffer-stretched preview."""
        native = self.render(settings, screen_width, screen_height)

        if not stretch_to_display:
            return native

        if display_width is None or display_height is None:
            raise ValueError(
                "display_width and display_height are required when stretching",
            )
        if stretch_filter not in ("nearest", "linear"):
            raise ValueError(f"unsupported stretch filter: {stretch_filter}")

        self._validate_resolution(display_width, display_height, "display")
        return self._stretch_to_display(
            native,
            game_width=screen_width,
            game_height=screen_height,
            display_width=display_width,
            display_height=display_height,
            stretch_filter=stretch_filter,
        )

    def render_pixel_map(
        self,
        settings: dict[str, SettingsValue],
    ) -> list[list[PixelCell]]:
        return self._image_to_pixel_map(self.render(settings))

    def render_pixel_map_for_resolution(
        self,
        settings: dict[str, SettingsValue],
        screen_width: int,
        screen_height: int,
        *,
        stretch_to_display: bool = False,
        display_width: int | None = None,
        display_height: int | None = None,
        stretch_filter: StretchFilter = "linear",
    ) -> list[list[PixelCell]]:
        image = self.render_for_resolution(
            settings,
            screen_width,
            screen_height,
            stretch_to_display=stretch_to_display,
            display_width=display_width,
            display_height=display_height,
            stretch_filter=stretch_filter,
        )
        return self._image_to_pixel_map(image)

    def render_scope_pixel_map(
        self,
        scope_width: int,
        screen_width: int,
        screen_height: int,
        *,
        stretch_to_display: bool = False,
        display_width: int | None = None,
        display_height: int | None = None,
        stretch_filter: StretchFilter = "linear",
    ) -> list[list[PixelCell]]:
        """Render a sniper-scope black crosshair pixel map.

        The scope crosshair is a simple black plus sign with the given
        *scope_width* (1–6, matching the in-game setting).  The arms extend
        ~8 % of the screen height from centre so the preview clearly shows
        the cross pattern around the centre.

        Resolution and stretch follow the same logic as the regular
        crosshair renderer.
        """
        self._validate_resolution(screen_width, screen_height, "game")

        arm_length = max(8, int(screen_height * 0.08))
        thickness = max(1, min(6, int(scope_width)))
        canvas_size = max(32, (arm_length + thickness + 4) * 2)
        if canvas_size % 2 != 0:
            canvas_size += 1

        image = QImage(canvas_size, canvas_size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor(0, 0, 0, 0))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        c = canvas_size // 2
        black = QColor(0, 0, 0, 255)

        # Horizontal bar
        painter.fillRect(c - arm_length, c - thickness // 2, arm_length * 2, thickness, black)
        # Vertical bar
        painter.fillRect(c - thickness // 2, c - arm_length, thickness, arm_length * 2, black)

        painter.end()

        pixel_map = self._image_to_pixel_map(image)
        # Crop to 5 game-pixels from centre so the grid widget stays small.
        # For even game dimensions the centre is between two pixels → even crop
        # (5 on each side = 10).  For odd game dimensions the centre is on a
        # pixel → odd crop (5 on each side + centre = 11).
        if pixel_map and pixel_map[0]:
            h, w = len(pixel_map), len(pixel_map[0])
            cy, cx = h // 2, w // 2

            def _crop_range(c: int, is_even: bool, limit: int) -> tuple[int, int]:
                end = c + 5 if is_even else c + 6
                return max(0, c - 5), min(end, limit)

            y_start, y_end = _crop_range(cy, screen_height % 2 == 0, h)
            x_start, x_end = _crop_range(cx, screen_width % 2 == 0, w)
            pixel_map = [row[x_start:x_end] for row in pixel_map[y_start:y_end]]

        if not stretch_to_display:
            return pixel_map

        if display_width is None or display_height is None:
            raise ValueError(
                "display_width and display_height are required when stretching",
            )
        if stretch_filter not in ("nearest", "linear"):
            raise ValueError(f"unsupported stretch filter: {stretch_filter}")

        self._validate_resolution(display_width, display_height, "display")
        stretched = self._stretch_to_display(
            image,
            game_width=screen_width,
            game_height=screen_height,
            display_width=display_width,
            display_height=display_height,
            stretch_filter=stretch_filter,
        )
        stretched_map = self._image_to_pixel_map(stretched)
        # Crop stretched map to 5 display-pixels from centre, parity-aware.
        if stretched_map and stretched_map[0]:
            h, w = len(stretched_map), len(stretched_map[0])
            cy, cx = h // 2, w // 2

            def _crop_stretched(c: int, is_even: bool, limit: int) -> tuple[int, int]:
                end = c + 5 if is_even else c + 6
                return max(0, c - 5), min(end, limit)

            y_start, y_end = _crop_stretched(cy, display_height % 2 == 0, h)
            x_start, x_end = _crop_stretched(cx, display_width % 2 == 0, w)
            stretched_map = [row[x_start:x_end] for row in stretched_map[y_start:y_end]]
        return stretched_map

    def resolved_metrics_for_resolution(
        self,
        settings: dict[str, SettingsValue],
        screen_width: int,
        screen_height: int,
    ) -> ResolvedMetrics:
        self._validate_resolution(screen_width, screen_height, "game")
        metrics = self._metrics(settings, screen_height)
        preview = self.render(settings, screen_width, screen_height)
        return {
            "length": metrics.length,
            "thickness": metrics.thickness,
            "gap": metrics.gap,
            "outline": metrics.outline,
            "canvas_size": max(preview.width(), preview.height()),
        }

    @staticmethod
    def count_lit_pixels(pixel_map: list[list[PixelCell]]) -> int:
        return sum(
            1
            for row in pixel_map
            for pixel in row
            if int(pixel["a"]) > 0
        )

    def _metrics(
        self,
        settings: dict[str, SettingsValue],
        screen_height: int,
    ) -> _Metrics:
        scale = screen_height / self.REFERENCE_HEIGHT

        length_1080 = self._resolve_length_1080(
            float(settings["cl_crosshairsize"]),
        )
        thickness_1080 = self._resolve_thickness_1080(
            float(settings["cl_crosshairthickness"]),
        )
        gap_1080 = self._resolve_gap_1080(
            float(settings["cl_crosshairgap"]),
        )

        length = max(
            0,
            self._round_half_away_from_zero(length_1080 * scale),
        )
        thickness = max(
            1,
            self._round_half_away_from_zero(thickness_1080 * scale),
        )
        gap = self._round_half_away_from_zero(gap_1080 * scale)

        outline = 0
        if bool(settings["cl_crosshair_drawoutline"]):
            raw_outline = max(
                0.0,
                float(settings["cl_crosshair_outlinethickness"]),
            )
            if raw_outline > 0.0:
                outline_1080 = max(
                    1,
                    self._round_half_away_from_zero(raw_outline),
                )
                outline = max(
                    1,
                    self._round_half_away_from_zero(outline_1080 * scale),
                )

        total_distance = gap + 2
        visible_length = max(1, length)

        # This is only a provisional drawing canvas. The final preview is
        # trimmed to the visible crosshair plus exactly one transparent pixel
        # on each side.
        extent = abs(total_distance) + visible_length + outline + thickness + 4
        canvas_size = max(16, extent * 2)
        if canvas_size % 2 != 0:
            canvas_size += 1

        return _Metrics(
            length=length,
            thickness=thickness,
            gap=gap,
            outline=outline,
            canvas_size=canvas_size,
            t_style=bool(settings["cl_crosshair_t"]),
        )

    def _arm_specs(
        self,
        axis_twice: int,
        metrics: _Metrics,
    ) -> list[_ArmSpec]:
        if metrics.length <= 0:
            return []

        total_distance = metrics.gap + 2
        adjusted_length = (
            metrics.length - 1
            if metrics.thickness == 1
            else metrics.length
        )
        arm_length = max(1, adjusted_length + 1)

        axis = axis_twice / 2.0
        negative_inner = math.floor(axis - total_distance)
        positive_inner = math.ceil(axis + total_distance)
        band_start = math.ceil(axis - (metrics.thickness / 2.0))

        color_rects = [
            _RectSpec(
                negative_inner - arm_length + 1,
                band_start,
                arm_length,
                metrics.thickness,
            ),
            _RectSpec(
                positive_inner,
                band_start,
                arm_length,
                metrics.thickness,
            ),
            _RectSpec(
                band_start,
                negative_inner - arm_length + 1,
                metrics.thickness,
                arm_length,
            ),
            _RectSpec(
                band_start,
                positive_inner,
                metrics.thickness,
                arm_length,
            ),
        ]

        arms = [
            _ArmSpec(
                color=rect,
                outline=(
                    self._expanded(rect, metrics.outline)
                    if metrics.outline > 0
                    else None
                ),
            )
            for rect in color_rects
        ]

        if metrics.t_style:
            # Order: left, right, top, bottom.
            del arms[2]

        return arms

    def _stretch_to_display(
        self,
        source: QImage,
        *,
        game_width: int,
        game_height: int,
        display_width: int,
        display_height: int,
        stretch_filter: StretchFilter,
    ) -> QImage:
        """Stretch using coordinates from the complete frame.

        Both game and display centres are treated as geometric centres. For an
        even resolution, that centre is the boundary between four pixels. No
        upper-left or lower-right member of the central 2x2 group is selected.
        """
        scale_x = display_width / game_width
        scale_y = display_height / game_height

        output_width = self._scaled_canvas_dimension(
            source.width(),
            scale_x,
            display_width,
        )
        output_height = self._scaled_canvas_dimension(
            source.height(),
            scale_y,
            display_height,
        )

        output = QImage(
            output_width,
            output_height,
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        output.fill(QColor(0, 0, 0, 0))

        # Matching parity makes both divisions exact integers and aligns each
        # crop with the geometric centre boundary of its complete frame.
        source_origin_x = (game_width - source.width()) // 2
        source_origin_y = (game_height - source.height()) // 2
        output_origin_x = (display_width - output_width) // 2
        output_origin_y = (display_height - output_height) // 2

        if stretch_filter == "nearest":
            self._sample_nearest(
                source,
                output,
                source_origin_x=source_origin_x,
                source_origin_y=source_origin_y,
                output_origin_x=output_origin_x,
                output_origin_y=output_origin_y,
                game_width=game_width,
                game_height=game_height,
                display_width=display_width,
                display_height=display_height,
            )
        else:
            self._sample_linear(
                source,
                output,
                source_origin_x=source_origin_x,
                source_origin_y=source_origin_y,
                output_origin_x=output_origin_x,
                output_origin_y=output_origin_y,
                game_width=game_width,
                game_height=game_height,
                display_width=display_width,
                display_height=display_height,
            )

        return output

    @staticmethod
    def _sample_nearest(
        source: QImage,
        output: QImage,
        *,
        source_origin_x: int,
        source_origin_y: int,
        output_origin_x: int,
        output_origin_y: int,
        game_width: int,
        game_height: int,
        display_width: int,
        display_height: int,
    ) -> None:
        source_x_for_output: list[int] = []
        for output_x in range(output.width()):
            display_x = output_origin_x + output_x
            game_x = math.floor(
                ((display_x + 0.5) * game_width) / display_width,
            )
            source_x_for_output.append(game_x - source_origin_x)

        for output_y in range(output.height()):
            display_y = output_origin_y + output_y
            game_y = math.floor(
                ((display_y + 0.5) * game_height) / display_height,
            )
            source_y = game_y - source_origin_y

            if not 0 <= source_y < source.height():
                continue

            for output_x, source_x in enumerate(source_x_for_output):
                if 0 <= source_x < source.width():
                    output.setPixel(
                        output_x,
                        output_y,
                        source.pixel(source_x, source_y),
                    )

    @classmethod
    def _sample_linear(
        cls,
        source: QImage,
        output: QImage,
        *,
        source_origin_x: int,
        source_origin_y: int,
        output_origin_x: int,
        output_origin_y: int,
        game_width: int,
        game_height: int,
        display_width: int,
        display_height: int,
    ) -> None:
        source_positions_x: list[float] = []
        for output_x in range(output.width()):
            display_x = output_origin_x + output_x
            game_x = (
                ((display_x + 0.5) * game_width) / display_width
            ) - 0.5
            source_positions_x.append(game_x - source_origin_x)

        for output_y in range(output.height()):
            display_y = output_origin_y + output_y
            game_y = (
                ((display_y + 0.5) * game_height) / display_height
            ) - 0.5
            source_y = game_y - source_origin_y

            for output_x, source_x in enumerate(source_positions_x):
                color = cls._bilinear_pixel(source, source_x, source_y)
                if color.alpha() > 0:
                    output.setPixelColor(output_x, output_y, color)

    @staticmethod
    def _bilinear_pixel(source: QImage, x: float, y: float) -> QColor:
        x0 = math.floor(x)
        y0 = math.floor(y)
        fraction_x = x - x0
        fraction_y = y - y0

        samples = (
            (x0, y0, (1.0 - fraction_x) * (1.0 - fraction_y)),
            (x0 + 1, y0, fraction_x * (1.0 - fraction_y)),
            (x0, y0 + 1, (1.0 - fraction_x) * fraction_y),
            (x0 + 1, y0 + 1, fraction_x * fraction_y),
        )

        alpha_sum = 0.0
        premultiplied_r = 0.0
        premultiplied_g = 0.0
        premultiplied_b = 0.0

        for sample_x, sample_y, weight in samples:
            if weight <= 0.0:
                continue
            if not (0 <= sample_x < source.width() and 0 <= sample_y < source.height()):
                continue

            color = source.pixelColor(sample_x, sample_y)
            alpha = color.alpha() / 255.0
            weighted_alpha = alpha * weight
            alpha_sum += weighted_alpha
            premultiplied_r += color.red() * weighted_alpha
            premultiplied_g += color.green() * weighted_alpha
            premultiplied_b += color.blue() * weighted_alpha

        if alpha_sum <= 0.0:
            return QColor(0, 0, 0, 0)

        alpha_byte = max(0, min(255, round(alpha_sum * 255.0)))
        return QColor(
            max(0, min(255, round(premultiplied_r / alpha_sum))),
            max(0, min(255, round(premultiplied_g / alpha_sum))),
            max(0, min(255, round(premultiplied_b / alpha_sum))),
            alpha_byte,
        )

    @classmethod
    def _scaled_canvas_dimension(
        cls,
        source_dimension: int,
        scale: float,
        target_frame_dimension: int,
    ) -> int:
        result = max(1, math.ceil(source_dimension * scale))

        # The preview and full target frame must have the same parity. With an
        # even display this places the centre on an edge between pixels; with
        # an odd display it places the centre through the middle pixel.
        if (result % 2) != (target_frame_dimension % 2):
            result += 1

        return result

    @staticmethod
    def _centered_square(axis_twice: int, size: int) -> _RectSpec:
        axis = axis_twice / 2.0
        start = math.ceil(axis - (size / 2.0))
        return _RectSpec(start, start, size, size)

    @staticmethod
    def _expanded(rect: _RectSpec, amount: int) -> _RectSpec:
        return _RectSpec(
            rect.x - amount,
            rect.y - amount,
            rect.width + (amount * 2),
            rect.height + (amount * 2),
        )

    @classmethod
    def _trim_to_content(cls, image: QImage, padding: int) -> QImage:
        min_x = image.width()
        min_y = image.height()
        max_x = -1
        max_y = -1

        for y in range(image.height()):
            for x in range(image.width()):
                if image.pixelColor(x, y).alpha() > 0:
                    if x < min_x:
                        min_x = x
                    if y < min_y:
                        min_y = y
                    if x > max_x:
                        max_x = x
                    if y > max_y:
                        max_y = y

        if max_x < min_x or max_y < min_y:
            # No visible pixels.
            return image

        left = max(0, min_x - padding)
        top = max(0, min_y - padding)
        right = min(image.width() - 1, max_x + padding)
        bottom = min(image.height() - 1, max_y + padding)

        return image.copy(
            left,
            top,
            right - left + 1,
            bottom - top + 1,
        )

    @staticmethod
    def _fill_rect(
        painter: QPainter,
        rect: _RectSpec,
        color: QColor,
    ) -> None:
        if rect.width <= 0 or rect.height <= 0:
            return
        painter.fillRect(
            QRect(rect.x, rect.y, rect.width, rect.height),
            color,
        )

    @classmethod
    def _resolve_length_1080(cls, value: float) -> int:
        if value <= _LENGTH_MAP_1080[-1][0]:
            return cls._threshold_value(_LENGTH_MAP_1080, value)
        return max(0, cls._round_half_away_from_zero(value * 2.25))

    @classmethod
    def _resolve_thickness_1080(cls, value: float) -> int:
        if value <= _THICKNESS_MAP_1080[-1][0]:
            return max(1, cls._threshold_value(_THICKNESS_MAP_1080, value))
        return max(1, cls._round_half_away_from_zero(value * 2.25))

    @classmethod
    def _resolve_gap_1080(cls, value: float) -> int:
        if _GAP_MAP_1080[0][0] <= value <= _GAP_MAP_1080[-1][0]:
            return cls._threshold_value(_GAP_MAP_1080, value)
        return cls._round_half_away_from_zero(value) + 3

    @staticmethod
    def _threshold_value(
        mapping: tuple[tuple[float, int], ...],
        value: float,
    ) -> int:
        result = mapping[0][1]
        for threshold, mapped_value in mapping:
            if value < threshold:
                break
            result = mapped_value
        return result

    @staticmethod
    def _round_half_away_from_zero(value: float) -> int:
        if value >= 0.0:
            return math.floor(value + 0.5)
        return math.ceil(value - 0.5)

    @staticmethod
    def _image_to_pixel_map(image: QImage) -> list[list[PixelCell]]:
        rows: list[list[PixelCell]] = []

        for y in range(image.height()):
            row: list[PixelCell] = []
            for x in range(image.width()):
                color = image.pixelColor(x, y)
                alpha = color.alpha()
                row.append(
                    {
                        "r": color.red(),
                        "g": color.green(),
                        "b": color.blue(),
                        "a": alpha,
                        "is_crosshair": alpha > 0,
                    },
                )
            rows.append(row)

        return rows

    @staticmethod
    def _validate_resolution(width: int, height: int, label: str) -> None:
        if width <= 0 or height <= 0:
            raise ValueError(f"{label} dimensions must be positive")

    @staticmethod
    def _alpha(settings: dict[str, SettingsValue]) -> int:
        if bool(settings["cl_crosshairusealpha"]):
            return max(0, min(255, int(settings["cl_crosshairalpha"])))
        return 255

    @staticmethod
    def _color(
        settings: dict[str, SettingsValue],
    ) -> tuple[int, int, int]:
        color_index = int(settings["cl_crosshaircolor"])
        if color_index == 5:
            return (
                max(0, min(255, int(settings["cl_crosshaircolor_r"]))),
                max(0, min(255, int(settings["cl_crosshaircolor_g"]))),
                max(0, min(255, int(settings["cl_crosshaircolor_b"]))),
            )
        return PRESET_COLORS.get(color_index, (0, 255, 0))
