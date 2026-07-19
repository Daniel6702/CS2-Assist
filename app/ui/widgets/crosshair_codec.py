"""CS2 crosshair codec — encode/decode CSGO-xxxxx crosshair share codes."""
from __future__ import annotations

import math
import re
from typing import ClassVar, Final

SettingValue = bool | float | int


class CS2CrosshairCodec:
    DICTIONARY: ClassVar[str] = "ABCDEFGHJKLMNOPQRSTUVWXYZabcdefhijkmnopqrstuvwxyz23456789"
    DEFAULT_SETTINGS: ClassVar[dict[str, SettingValue]] = {
        "cl_crosshairalpha": 255,
        "cl_crosshaircolor": 5,
        "cl_crosshaircolor_b": 50,
        "cl_crosshaircolor_g": 250,
        "cl_crosshaircolor_r": 50,
        "cl_crosshairdot": False,
        "cl_crosshairgap": -2.0,
        "cl_crosshairsize": 2.0,
        "cl_crosshairstyle": 4,
        "cl_crosshairusealpha": True,
        "cl_crosshairthickness": 1.0,
        "cl_crosshair_drawoutline": True,
        "cl_crosshair_outlinethickness": 1.0,
        "cl_crosshair_dynamic_maxdist_splitratio": 0.35,
        "cl_crosshair_dynamic_splitalpha_innermod": 1.0,
        "cl_crosshair_dynamic_splitalpha_outermod": 0.5,
        "cl_crosshair_dynamic_splitdist": 7,
        "cl_crosshair_t": False,
        "cl_fixedcrosshairgap": -2.0,
        "cl_crosshairgap_useweaponvalue": False,
        "cl_crosshair_recoil": False,
    }

    _CODE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^CSGO(-[ABCDEFGHJKLMNOPQRSTUVWXYZabcdefhijkmnopqrstuvwxyz23456789]{5}){5}$",
    )
    _RAW_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^[ABCDEFGHJKLMNOPQRSTUVWXYZabcdefhijkmnopqrstuvwxyz23456789]{25}$",
    )
    _BYTE_COUNT: ClassVar[int] = 18
    _CODE_LENGTH: ClassVar[int] = 25
    _PRESET_COLORS: ClassVar[dict[int, tuple[int, int, int]]] = {
        0: (255, 0, 0),
        1: (0, 255, 0),
        2: (255, 255, 0),
        3: (0, 0, 255),
        4: (0, 255, 255),
    }

    def parse_code(self, code: str) -> dict[str, SettingValue]:
        clean_code = self._normalize_code(code.strip())
        if self._CODE_PATTERN.fullmatch(clean_code) is None:
            return self.DEFAULT_SETTINGS.copy()

        chars = clean_code[5:].replace("-", "")
        number = self._decode_base58(chars)
        byte_values = self._number_to_js_bytes(number)

        checksum = byte_values[0]
        calculated_checksum = sum(byte_values[1:]) % 256
        if checksum != calculated_checksum:
            return self.DEFAULT_SETTINGS.copy()

        return {
            "cl_crosshairgap": self.signed_byte(byte_values[2]) / 10,
            "cl_crosshair_outlinethickness": byte_values[3] / 2,
            "cl_crosshaircolor_r": byte_values[4],
            "cl_crosshaircolor_g": byte_values[5],
            "cl_crosshaircolor_b": byte_values[6],
            "cl_crosshairalpha": byte_values[7],
            "cl_crosshair_dynamic_splitdist": byte_values[8] & 0x7F,
            "cl_crosshair_recoil": ((byte_values[8] >> 7) & 1) == 1,
            "cl_fixedcrosshairgap": self.signed_byte(byte_values[9]) / 10,
            "cl_crosshaircolor": byte_values[10] & 7,
            "cl_crosshair_drawoutline": (byte_values[10] & 8) == 8,
            "cl_crosshair_dynamic_splitalpha_innermod": (byte_values[10] >> 4) / 10,
            "cl_crosshair_dynamic_splitalpha_outermod": (byte_values[11] & 0xF) / 10,
            "cl_crosshair_dynamic_maxdist_splitratio": (byte_values[11] >> 4) / 10,
            "cl_crosshairthickness": byte_values[12] / 10,
            "cl_crosshairstyle": (byte_values[13] & 0xF) >> 1,
            "cl_crosshairdot": ((byte_values[13] >> 4) & 1) == 1,
            "cl_crosshairgap_useweaponvalue": ((byte_values[13] >> 5) & 1) == 1,
            "cl_crosshairusealpha": ((byte_values[13] >> 6) & 1) == 1,
            "cl_crosshair_t": ((byte_values[13] >> 7) & 1) == 1,
            "cl_crosshairsize": (((byte_values[15] & 0x1F) << 8) + byte_values[14]) / 10,
        }

    def generate_code(self, settings: dict[str, SettingValue]) -> str:
        byte_values = [0] * self._BYTE_COUNT
        byte_values[1] = 1
        byte_values[2] = self._js_round(settings["cl_crosshairgap"] * 10) & 0xFF
        byte_values[3] = self._js_round(settings["cl_crosshair_outlinethickness"] * 2)
        byte_values[4] = self._js_round(settings["cl_crosshaircolor_r"])
        byte_values[5] = self._js_round(settings["cl_crosshaircolor_g"])
        byte_values[6] = self._js_round(settings["cl_crosshaircolor_b"])
        byte_values[7] = self._js_round(settings["cl_crosshairalpha"])
        byte_values[8] = (self._js_round(settings["cl_crosshair_dynamic_splitdist"]) & 0x7F) | (
            0x80 if settings["cl_crosshair_recoil"] else 0
        )
        byte_values[9] = self._js_round(settings["cl_fixedcrosshairgap"] * 10) & 0xFF
        byte_values[10] = (
            (self._js_round(settings["cl_crosshaircolor"]) & 7)
            | (8 if settings["cl_crosshair_drawoutline"] else 0)
            | ((self._js_round(settings["cl_crosshair_dynamic_splitalpha_innermod"] * 10) & 0xF) << 4)
        )
        byte_values[11] = (self._js_round(settings["cl_crosshair_dynamic_splitalpha_outermod"] * 10) & 0xF) | (
            (self._js_round(settings["cl_crosshair_dynamic_maxdist_splitratio"] * 10) & 0xF) << 4
        )
        byte_values[12] = self._js_round(settings["cl_crosshairthickness"] * 10)
        byte_values[13] = (
            ((self._js_round(settings["cl_crosshairstyle"]) & 0xF) << 1)
            | (0x10 if settings["cl_crosshairdot"] else 0)
            | (0x20 if settings["cl_crosshairgap_useweaponvalue"] else 0)
            | (0x40 if settings["cl_crosshairusealpha"] else 0)
            | (0x80 if settings["cl_crosshair_t"] else 0)
        )

        size_value = self._js_round(settings["cl_crosshairsize"] * 10)
        byte_values[14] = size_value & 0xFF
        byte_values[15] = (size_value >> 8) & 0x1F
        byte_values[0] = sum(byte_values[1:]) & 0xFF

        number = int.from_bytes(bytes(byte_values), byteorder="big")
        result = ""
        for _ in range(self._CODE_LENGTH):
            number, remainder = divmod(number, len(self.DICTIONARY))
            result += self.DICTIONARY[remainder]

        return "CSGO-{}-{}-{}-{}-{}".format(
            result[:5],
            result[5:10],
            result[10:15],
            result[15:20],
            result[20:],
        )

    @staticmethod
    def signed_byte(x: int) -> int:
        return (x ^ 0x80) - 0x80

    def get_color(self, settings: dict[str, SettingValue]) -> tuple[int, int, int]:
        color_index = int(settings["cl_crosshaircolor"])
        if color_index == 5:
            return (
                int(settings["cl_crosshaircolor_r"]),
                int(settings["cl_crosshaircolor_g"]),
                int(settings["cl_crosshaircolor_b"]),
            )
        return self._PRESET_COLORS.get(color_index, (0, 255, 0))

    def _normalize_code(self, clean_code: str) -> str:
        if clean_code.startswith("CSGO-"):
            return clean_code
        if self._RAW_PATTERN.fullmatch(clean_code) is None:
            return clean_code
        return "CSGO-{}-{}-{}-{}-{}".format(
            clean_code[:5],
            clean_code[5:10],
            clean_code[10:15],
            clean_code[15:20],
            clean_code[20:],
        )

    def _decode_base58(self, chars: str) -> int:
        number = 0
        for char in reversed(chars):
            index = self.DICTIONARY.find(char)
            if index == -1:
                return 0
            number = (number * len(self.DICTIONARY)) + index
        return number

    @classmethod
    def _number_to_js_bytes(cls, number: int) -> list[int]:
        hex_number = f"{number:x}".rjust(cls._BYTE_COUNT * 2, "0")
        return [int(hex_number[index: index + 2], 16) for index in range(0, len(hex_number), 2)]

    @staticmethod
    def _js_round(value: SettingValue) -> int:
        return math.floor(float(value) + 0.5)
