"""The factor registry: one id, one family, one reader.

The family is what the grid check counts, so it lives next to the reader that
decides where the input comes from. A spec that names an id not listed here is
refused; the registry is the closed vocabulary the model writes in.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .snapshot import Snapshot

MOMENTUM_BARS = 126  # about six months of trading days


@dataclass(frozen=True)
class Factor:
    id: str
    family: str
    read: Callable[[Snapshot, str, str], float | None]


def _fact(key: str) -> Callable[[Snapshot, str, str], float | None]:
    return lambda snap, symbol, date: snap.fact_at(symbol, key, date)


def _momentum_6m(snap: Snapshot, symbol: str, date: str) -> float | None:
    then = snap.offset(date, MOMENTUM_BARS)
    if then is None:
        return None
    now_p, then_p = snap.price_at(symbol, date), snap.price_at(symbol, then)
    if now_p is None or then_p is None or then_p <= 0:
        return None
    return now_p / then_p - 1


REGISTRY: dict[str, Factor] = {
    f.id: f
    for f in (
        Factor("debt_ratio", "fundamental", _fact("debt_ratio")),
        Factor("dividend_yield", "fundamental", _fact("dividend_yield")),
        Factor("momentum_6m", "momentum", _momentum_6m),
    )
}


def factor(factor_id: str) -> Factor:
    try:
        return REGISTRY[factor_id]
    except KeyError:
        raise ValueError(f"unknown factor {factor_id!r}; registered: {sorted(REGISTRY)}") from None
