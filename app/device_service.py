from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Any

try:
    from evdev import InputDevice, ecodes, list_devices
except ImportError:  # pragma: no cover
    InputDevice = None
    ecodes = None
    list_devices = None


@dataclass(frozen=True)
class DeviceInfo:
    path: str
    name: str
    capabilities: tuple[str, ...]

    @property
    def label(self) -> str:
        caps = ", ".join(self.capabilities)
        return f"{self.name} [{self.path}] ({caps})"


class DeviceService:
    def __init__(self) -> None:
        self.system = platform.system()

    def list_keyboards(self) -> list[DeviceInfo]:
        if self.system != "Linux" or InputDevice is None or ecodes is None or list_devices is None:
            return []
        found: list[DeviceInfo] = []
        for path in list_devices():
            try:
                dev = InputDevice(path)
                keys = set(dev.capabilities().get(ecodes.EV_KEY, []))
            except Exception:
                continue
            caps: list[str] = []
            if ecodes.KEY_SPACE in keys:
                caps.append("space")
            if {ecodes.KEY_W, ecodes.KEY_A, ecodes.KEY_S, ecodes.KEY_D}.issubset(keys):
                caps.append("movement")
            if keys and caps:
                found.append(DeviceInfo(path=path, name=dev.name or path, capabilities=tuple(caps)))
        found.sort(key=lambda item: (item.name.lower(), item.path))
        return found

    def list_monitors(self) -> list[dict[str, Any]]:
        try:
            from mss import mss
        except Exception:
            return []
        with mss() as sct:
            monitors: list[dict[str, Any]] = []
            for index, mon in enumerate(sct.monitors):
                label = "all monitors combined" if index == 0 else f"monitor {index}"
                monitors.append(
                    {
                        "index": index,
                        "label": label,
                        "left": mon["left"],
                        "top": mon["top"],
                        "width": mon["width"],
                        "height": mon["height"],
                    }
                )
            return monitors
