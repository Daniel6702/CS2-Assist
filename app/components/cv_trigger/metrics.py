from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from time import perf_counter_ns
from types import TracebackType
from typing import Final

JSONScalar = bool | int | float | str | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

_NS_PER_MS: Final = 1_000_000.0


@dataclass(frozen=True, slots=True)
class MetricSummary:
    count: int
    total: float
    avg: float
    min: float
    max: float

    def as_json(self) -> dict[str, JSONValue]:
        return {
            "count": self.count,
            "total": self.total,
            "avg": self.avg,
            "min": self.min,
            "max": self.max,
        }


class CVPerfStats:
    def __init__(self, *, enabled: bool) -> None:
        self.enabled = enabled
        self._timings: dict[str, list[float]] = defaultdict(list)
        self._counts: dict[str, int] = defaultdict(int)

    def record_ms(self, name: str, value: float) -> None:
        if self.enabled:
            self._timings[name].append(float(value))

    def record_count(self, name: str, value: int = 1) -> None:
        if self.enabled:
            self._counts[name] += int(value)

    def timer(self, name: str) -> "PerfTimer":
        return PerfTimer(stats=self, name=name)

    def summary(self, *, extra: dict[str, JSONValue] | None = None) -> dict[str, JSONValue]:
        if not self.enabled:
            return {}
        out: dict[str, JSONValue] = {}
        for name, values in self._timings.items():
            if not values:
                continue
            total = sum(values)
            out[name] = MetricSummary(
                count=len(values),
                total=total,
                avg=total / len(values),
                min=min(values),
                max=max(values),
            ).as_json()
        out.update(self._counts)
        if extra is not None:
            out.update(extra)
        return out


class PerfTimer:
    def __init__(self, *, stats: CVPerfStats, name: str) -> None:
        self._stats = stats
        self._name = name
        self._started_ns = 0

    def __enter__(self) -> "PerfTimer":
        if self._stats.enabled:
            self._started_ns = perf_counter_ns()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if self._stats.enabled and self._started_ns:
            elapsed_ms = (perf_counter_ns() - self._started_ns) / _NS_PER_MS
            self._stats.record_ms(self._name, elapsed_ms)
        return False


def disabled_perf_stats() -> CVPerfStats:
    return CVPerfStats(enabled=False)
