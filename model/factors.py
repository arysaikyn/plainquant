"""The factor registry: one id, one family, one reader.

The family is what the grid check counts, so it lives next to the reader that
decides where the input comes from. A spec that names an id not listed here is
refused; the registry is the closed vocabulary the model writes in.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .snapshot import Snapshot
from .stats import sd

MOMENTUM_BARS = 126  # about six months of trading days
YEAR_BARS = 252
MONTH_BARS = 21
VOLATILITY_BARS = 60


@dataclass(frozen=True)
class Factor:
    id: str
    family: str
    read: Callable[[Snapshot, str, str], float | None]


def _fact(key: str) -> Callable[[Snapshot, str, str], float | None]:
    return lambda snap, symbol, date: snap.fact_at(symbol, key, date)


def _change(snap: Snapshot, symbol: str, date: str, bars_back: int, bars_end: int = 0) -> float | None:
    """Price change from `bars_back` trading days before `date` to `bars_end` days before it."""
    days = snap.trailing(date, bars_back)
    if days is None:
        return None
    start, end = snap.price_at(symbol, days[0]), snap.price_at(symbol, days[len(days) - 1 - bars_end])
    if start is None or end is None or start <= 0:
        return None
    return end / start - 1


def _momentum_6m(snap: Snapshot, symbol: str, date: str) -> float | None:
    return _change(snap, symbol, date, MOMENTUM_BARS)


def _momentum_12_1(snap: Snapshot, symbol: str, date: str) -> float | None:
    """The year's change leaving out the last month, which tends to reverse."""
    return _change(snap, symbol, date, YEAR_BARS, MONTH_BARS)


def _return_1m(snap: Snapshot, symbol: str, date: str) -> float | None:
    return _change(snap, symbol, date, MONTH_BARS)


def _volatility_60d(snap: Snapshot, symbol: str, date: str) -> float | None:
    days = snap.trailing(date, VOLATILITY_BARS)
    if days is None:
        return None
    prices = [snap.price_at(symbol, d) for d in days]
    if any(p is None or p <= 0 for p in prices):
        return None
    return sd([b / a - 1 for a, b in zip(prices, prices[1:])])


REGISTRY: dict[str, Factor] = {
    f.id: f
    for f in (
        Factor("debt_ratio", "fundamental", _fact("debt_ratio")),
        Factor("dividend_yield", "fundamental", _fact("dividend_yield")),
        Factor("momentum_6m", "momentum", _momentum_6m),
        Factor("momentum_12_1", "momentum", _momentum_12_1),
        Factor("return_1m", "reversal", _return_1m),
        Factor("volatility_60d", "volatility", _volatility_60d),
    )
}


def factor(factor_id: str) -> Factor:
    try:
        return REGISTRY[factor_id]
    except KeyError:
        raise ValueError(f"unknown factor {factor_id!r}; registered: {sorted(REGISTRY)}") from None
