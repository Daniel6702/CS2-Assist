from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Callable

XrandrRunner = Callable[..., str]


class XrandrError(RuntimeError):
    pass


@dataclass(frozen=True)
class DisplayState:
    brightness: float
    gamma_r: float
    gamma_g: float
    gamma_b: float


def run_xrandr(*arguments: str) -> str:
    result = subprocess.run(
        ["xrandr", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=3.0,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown xrandr error"
        raise XrandrError(f"xrandr failed: {detail}")
    return result.stdout


def connected_outputs_from_query(text: str) -> list[str]:
    outputs: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^(\S+)\s+connected\b", line)
        if match is not None:
            outputs.append(match.group(1))
    return outputs


def list_connected_outputs(runner: XrandrRunner = run_xrandr) -> list[str]:
    return connected_outputs_from_query(runner("--query"))


def detect_output(runner: XrandrRunner = run_xrandr) -> str:
    text = runner("--query")
    connected_outputs: list[str] = []
    primary_output: str | None = None
    for line in text.splitlines():
        match = re.match(r"^(\S+)\s+connected\b", line)
        if match is None:
            continue
        output_name = match.group(1)
        connected_outputs.append(output_name)
        if re.search(r"\bprimary\b", line):
            primary_output = output_name
    if primary_output is not None:
        return primary_output
    if connected_outputs:
        return connected_outputs[0]
    raise XrandrError("No connected XRandR output was found")


def read_display_state(output: str, runner: XrandrRunner = run_xrandr) -> DisplayState:
    text = runner("--verbose")
    current_output: str | None = None
    brightness: float | None = None
    gamma: tuple[float, float, float] | None = None
    for line in text.splitlines():
        output_header = re.match(r"^(\S+)\s+(connected|disconnected)\b", line)
        if output_header is not None:
            current_output = output_header.group(1)
            continue
        if current_output != output:
            continue
        stripped = line.strip()
        if stripped.startswith("Brightness:"):
            brightness = float(stripped.split(":", 1)[1].strip())
        elif stripped.startswith("Gamma:"):
            values = stripped.split(":", 1)[1].strip().split(":")
            if len(values) == 3:
                gamma = (float(values[0]), float(values[1]), float(values[2]))
    if brightness is None or gamma is None:
        raise XrandrError(f"Could not read brightness and gamma for output {output!r}")
    return DisplayState(brightness=brightness, gamma_r=gamma[0], gamma_g=gamma[1], gamma_b=gamma[2])
