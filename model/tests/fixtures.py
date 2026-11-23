"""A synthetic snapshot. No vendor data: every number comes from a seeded generator."""

from __future__ import annotations

import copy
import math
import random
from datetime import date, timedelta

from ..snapshot import Snapshot

SPEC = {
    "spec_version": "1.0",
    "market": "cn_a",
    "universe": "synthetic",
    "sharia": "off",
    "filters": [{"factor": "debt_ratio", "op": "lt", "value": 0.9}],
    "rank": [
        {"factor": "debt_ratio", "direction": "asc"},
        {"factor": "dividend_yield", "direction": "desc"},
    ],
    "top_k": 10,
    "n_drop": 2,
    "rebalance": "M",
    "period": {"start": "2020-01-01", "end": "2024-12-31"},
    "costs": {"fee_rate": 0.0015, "slip_rate": 0.005},
}


def spec(**changes) -> dict:
    out = copy.deepcopy(SPEC)
    out.update(changes)
    return out


def weekdays(start: date, end: date) -> list[str]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def make_snapshot(seed: int = 1, n: int = 40, flat: bool = False) -> Snapshot:
    rng = random.Random(seed)
    dates = weekdays(date(2019, 1, 1), date(2024, 12, 31))
    prices, facts, membership, names = {}, {}, {}, {}
    for i in range(n):
        symbol = f"S{i:03d}"
        names[symbol] = f"Name {i}"
        membership[symbol] = (dates[0], None)
        level, series = 100.0, {}
        drift, vol = rng.uniform(-0.0001, 0.0006), rng.uniform(0.008, 0.02)
        for d in dates:
            if not flat:
                level *= math.exp(drift + vol * rng.gauss(0, 1))
            series[d] = level
        prices[symbol] = series
        rows = []
        for year in range(2019, 2025):
            rows.append(
                (
                    f"{year}-04-30",
                    {
                        "debt_ratio": rng.uniform(0.05, 0.95),
                        "dividend_yield": rng.uniform(0.0, 0.06),
                        "interest_bearing_ratio": rng.uniform(0.02, 0.5),
                        "impure_income_ratio": rng.uniform(0.0, 0.08),
                        "receivables_ratio": None if rng.random() < 0.15 else rng.uniform(0.05, 0.5),
                    },
                )
            )
        facts[symbol] = rows
    return Snapshot(
        version=f"synthetic-seed{seed}",
        universe="synthetic",
        dates=dates,
        prices=prices,
        facts=facts,
        membership=membership,
        names=names,
    )
