"""Run a spec over its period on a snapshot.

Equal weight, rebalanced at the end of each period. A name with no price on the fill day is
suspended: it is not bought, and a name that should be sold is kept. The seller pays the
market's stamp duty on the value sold, at the rate in force on the fill day. The ranking uses the close of the
rebalance day; the trade is filled at the close of the NEXT trading day. Ranking and filling
on the same close would let the strategy trade at a price it had already seen. At the end of
the data, where no next day exists, the last day stands in. Cost is
charged on every unit traded, buys and sells alike: `sum |dw| * (fee + slip)`. The
weights are the target weights at each rebalance, so drift inside a period is not
modelled. The first formation pays the cost of buying the whole book but is left
out of the turnover metric, which is the steady-state one-way share per year.

The benchmark is the equal-weighted universe on the same dates, so the grid check
has a curve to measure the path against.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from datetime import date as _date

from . import markets
from .screen import screen, select
from .snapshot import Snapshot
from .stats import mean, sd

PERIODS_PER_YEAR = {"D": 252, "W": 52, "M": 12, "Q": 4, "A": 1}


def _period_key(freq: str, iso: str):
    d = _date.fromisoformat(iso)
    if freq == "D":
        return iso
    if freq == "W":
        return d.isocalendar()[:2]
    if freq == "M":
        return (d.year, d.month)
    if freq == "Q":
        return (d.year, (d.month - 1) // 3)
    return d.year


def marks_of(snap: Snapshot, freq: str, start: str, end: str) -> list[str]:
    """The first day in the window, then the last trading day of each period after it."""
    window = [d for d in snap.dates if start <= d <= end]
    if not window:
        return []
    last_of: dict = {}
    for d in window:
        last_of[_period_key(freq, d)] = d
    return [window[0]] + [d for d in last_of.values() if d > window[0]]


def fill_date(snap: Snapshot, day: str) -> str:
    """The trading day after `day`, or `day` itself when the data ends there."""
    i = bisect_right(snap.dates, day)
    return snap.dates[i] if i < len(snap.dates) else day


def tradable_book(snap: Snapshot, held: list[str], target: list[str], day: str) -> list[str]:
    """`target` after the day's suspensions. A name with no price that day cannot be traded:
    a new name is not bought (its slot stays empty), a name that should go is kept."""
    bought = [s for s in target if s in held or day in snap.prices.get(s, {})]
    stuck = [s for s in held if s not in bought and day not in snap.prices.get(s, {})]
    return bought + stuck


def _period_return(snap: Snapshot, symbols: list[str], a: str, b: str) -> float:
    rets = []
    for s in symbols:
        p0, p1 = snap.price_at(s, a), snap.price_at(s, b)
        rets.append(p1 / p0 - 1 if p0 and p1 else 0.0)
    return mean(rets)


def run_backtest(spec: dict, snap: Snapshot) -> dict:
    marks = marks_of(snap, spec["rebalance"], spec["period"]["start"], spec["period"]["end"])
    if len(marks) < 2:
        raise ValueError("period holds fewer than two rebalance dates")
    ppy = PERIODS_PER_YEAR[spec["rebalance"]]
    rate = spec["costs"]["fee_rate"] + spec["costs"]["slip_rate"]

    held: list[str] = []
    curve, bench = [1.0], [1.0]
    period_rets: list[float] = []
    traded: list[float] = []
    fills = [fill_date(snap, m) for m in marks]
    books: list[list[str]] = []
    for i, (a, b) in enumerate(zip(marks, marks[1:])):
        fa, fb = fills[i], fills[i + 1]
        target = tradable_book(snap, held, select(held, screen(spec, snap, a), spec["top_k"], spec["n_drop"]), fa)
        books.append(target)
        w_old = {s: 1 / len(held) for s in held}
        w_new = {s: 1 / len(target) for s in target}
        delta = sum(abs(w_new.get(s, 0.0) - w_old.get(s, 0.0)) for s in set(w_old) | set(w_new))
        traded.append(delta)
        sold = sum(max(0.0, w_old[s] - w_new.get(s, 0.0)) for s in w_old)
        tax = sold * markets.sell_tax_rate(spec["market"], fa)
        net = _period_return(snap, target, fa, fb) - delta * rate - tax
        period_rets.append(net)
        curve.append(curve[-1] * (1 + net))
        bench.append(bench[-1] * (1 + _period_return(snap, snap.universe_at(a), fa, fb)))
        held = target

    final_ranked = screen(spec, snap, marks[-1])
    final = select(held, final_ranked, spec["top_k"], spec["n_drop"])

    n = len(period_rets)
    low, peak = 0.0, curve[0]
    for v in curve:
        peak = max(peak, v)
        low = min(low, v / peak - 1)
    spread = sd(period_rets)
    steady = traded[1:]
    return {
        "dates": fills,  # the days the book was filled; `as_of` stays the last ranking day
        "curve": curve,
        "bench": bench,
        "metrics": {
            "annual_return": curve[-1] ** (ppy / n) - 1 if curve[-1] > 0 else -1.0,
            "max_drawdown": low,
            "sharpe": mean(period_rets) / spread * math.sqrt(ppy) if spread > 0 else 0.0,
            "turnover": mean(steady) / 2 * ppy if steady else 0.0,
        },
        "books": books,  # what was held after each fill; not part of the Result
        "as_of": marks[-1],
        "final": final,
        "final_ranked": final_ranked,
    }
