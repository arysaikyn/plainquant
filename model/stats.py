"""The two sample moments the engine shares. Port of web/src/lib/stats.ts."""

from __future__ import annotations

import math
from collections.abc import Sequence


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def sd(xs: Sequence[float]) -> float:
    """Sample standard deviation (n - 1). Zero for a constant or single value."""
    n = len(xs)
    if n < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
