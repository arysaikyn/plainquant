"""One date: Sharia filter, then hard filters, then rank. And the top-k / n-drop swap.

Order is the product rule. The Sharia screen runs before ranking, a name it cannot
prove is out, and a name missing any input the spec reads is out too: it is never
ranked on a zero.
"""

from __future__ import annotations

from . import sharia
from .factors import factor
from .snapshot import Snapshot
from .stats import mean, sd

_OPS = {
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
}


def sharia_at(snap: Snapshot, symbol: str, date: str) -> dict:
    return sharia.verdict(lambda key: snap.fact_at(symbol, key, date))


def screen(spec: dict, snap: Snapshot, date: str) -> list[dict]:
    """Ranked survivors, best first: [{symbol, score, factors, sharia}]."""
    survivors = []
    for symbol in snap.universe_at(date):
        if snap.price_at(symbol, date) is None:
            continue  # cannot be traded
        status = sharia_at(snap, symbol, date)["status"]
        if spec["sharia"] == "compliant_only" and status != "compliant":
            continue
        values: dict[str, float] = {}
        ok = True
        for flt in spec["filters"]:
            value = factor(flt["factor"]).read(snap, symbol, date)
            if value is None or not _OPS[flt["op"]](value, flt["value"]):
                ok = False
                break
            values[flt["factor"]] = value
        if not ok:
            continue
        for rank in spec["rank"]:
            value = factor(rank["factor"]).read(snap, symbol, date)
            if value is None:
                ok = False
                break
            values[rank["factor"]] = value
        if ok:
            survivors.append({"symbol": symbol, "factors": values, "sharia": status})

    z: dict[str, dict[str, float]] = {}
    for rank in spec["rank"]:
        column = [s["factors"][rank["factor"]] for s in survivors]
        m, spread = mean(column), sd(column)
        sign = 1.0 if rank["direction"] == "desc" else -1.0
        z[rank["factor"]] = {
            s["symbol"]: sign * ((s["factors"][rank["factor"]] - m) / spread if spread > 0 else 0.0)
            for s in survivors
        }
    for s in survivors:
        s["score"] = mean([z[r["factor"]][s["symbol"]] for r in spec["rank"]])
    return sorted(survivors, key=lambda s: (-s["score"], s["symbol"]))


def select(held: list[str], ranked: list[dict], top_k: int, n_drop: int) -> list[str]:
    """Top-k with churn: a name leaves when it stops being rankable, or when it is
    among the `n_drop` worst held and a better name is waiting. Nothing else sells.
    """
    order = {s["symbol"]: i for i, s in enumerate(ranked)}
    kept = [s for s in held if s in order]  # failed a filter or the screen: forced out
    kept.sort(key=lambda s: order[s])
    candidates = [s["symbol"] for s in ranked if s["symbol"] not in kept]
    vacancies = max(0, top_k - len(kept))
    swaps = min(n_drop, len(kept), max(0, len(candidates) - vacancies))
    if swaps:
        kept = kept[: len(kept) - swaps]
    return kept + candidates[: max(0, top_k - len(kept))]
