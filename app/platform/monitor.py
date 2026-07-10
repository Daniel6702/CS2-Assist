from __future__ import annotations

from dataclasses import dataclass
from functools import cache


@dataclass(frozen=True, slots=True)
class MonitorGeometry:
    left: int
    top: int
    width: int
    height: int

    def as_capture_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


def primary_monitor_geometry() -> MonitorGeometry:
    from mss import mss

    with mss() as screen_capture:
        monitors = screen_capture.monitors
        monitor = monitors[1] if len(monitors) > 1 else monitors[0]
        return MonitorGeometry(
            left=0,
            top=0,
            width=int(monitor["width"]),
            height=int(monitor["height"]),
        )


@cache
def default_monitor_geometry() -> MonitorGeometry:
    try:
        return primary_monitor_geometry()
    except (ImportError, IndexError, KeyError, OSError, RuntimeError, TypeError):
        return MonitorGeometry(left=0, top=0, width=2560, height=1440)
