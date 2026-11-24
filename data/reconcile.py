"""Does the snapshot's own market return look like the market? A coarse check.

    PYTHONPATH=<dir holding baostock> python3 -m data.reconcile data/raw/csi300

It compares the snapshot's equal-weighted universe, as the engine measures it (the
benchmark of every run, on the fill days), with the published CSI 300 price index over the
same days. The two differ on purpose: the index is weighted by market value and leaves out
dividends, the benchmark is equal-weighted and reinvests them. So this catches gross errors
(dates shifted, a wrong adjustment, a broken universe), not small ones. Two numbers: how
closely the monthly returns move together, and how far apart the annual returns are. The
limits are constants; they were set after the first real run, from what that run showed.
"""

from __future__ import annotations

import argparse
import math
import sys
from bisect import bisect_right

from model import store
from model.backtest import run_backtest
from model.stats import mean, sd

MIN_CORRELATION = 0.90
MAX_ANNUAL_GAP = 0.08
INDEX_CODE = "sh.000300"


def _at(closes: dict[str, float], day: str) -> float | None:
    days = sorted(closes)
    i = bisect_right(days, day)
    return closes[days[i - 1]] if i else None


def compare(dates: list[str], bench: list[float], index: dict[str, float], periods_per_year: int = 12) -> dict:
    """Monthly returns of the benchmark curve against the index closes on the same days."""
    marks = [_at(index, d) for d in dates]
    if any(m is None for m in marks):
        raise ValueError("the index has no close on or before the first benchmark day")
    ours = [b / a - 1 for a, b in zip(bench, bench[1:])]
    theirs = [b / a - 1 for a, b in zip(marks, marks[1:])]
    n = len(ours)
    mo, mt = mean(ours), mean(theirs)
    so, st = sd(ours), sd(theirs)
    corr = sum((x - mo) * (y - mt) for x, y in zip(ours, theirs)) / ((n - 1) * so * st) if so and st else 0.0
    annual = lambda curve: curve[-1] ** (periods_per_year / n) - 1 if curve[-1] > 0 else -1.0
    ours_annual, theirs_annual = annual(bench), annual([m / marks[0] for m in marks])
    return {
        "periods": n,
        "correlation": corr,
        "annual_ours": ours_annual,
        "annual_index": theirs_annual,
        "gap": ours_annual - theirs_annual,
        "ok": corr >= MIN_CORRELATION and abs(ours_annual - theirs_annual) <= MAX_ANNUAL_GAP,
    }


def main(argv: list[str] | None = None, bs=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m data.reconcile", description=__doc__.split("\n\n")[0])
    ap.add_argument("snapshot")
    args = ap.parse_args(argv)
    snap = store.load(args.snapshot)
    spec = {
        "spec_version": "1.0", "market": snap.market, "universe": snap.universe, "sharia": "off", "filters": [],
        "rank": [{"factor": "debt_ratio", "direction": "asc"}], "top_k": 5, "n_drop": 0, "rebalance": "M",
        "period": {"start": snap.dates[0], "end": snap.dates[-1]}, "costs": {"fee_rate": 0.0, "slip_rate": 0.0},
    }
    run = run_backtest(spec, snap)
    if bs is None:
        import baostock as bs
    login = bs.login()
    if login.error_code != "0":
        print(f"data: login failed: {login.error_code} {login.error_msg}", file=sys.stderr)
        return 2
    try:
        from data.baostock_source import closes

        index = closes(bs, INDEX_CODE, run["dates"][0], run["dates"][-1], "3")
    finally:
        bs.logout()
    got = compare(run["dates"], run["bench"], index)
    print(f"{snap.universe}: {got['periods']} monthly periods, {run['dates'][0]} to {run['dates'][-1]}")
    print(f"correlation of monthly returns with the CSI 300 index: {got['correlation']:.3f} (needs {MIN_CORRELATION})")
    print(f"annual return: snapshot equal-weight {got['annual_ours']:+.1%}, index {got['annual_index']:+.1%}, gap {got['gap']:+.1%} (limit {MAX_ANNUAL_GAP:.0%})")
    print("OK" if got["ok"] else "CHECK: the snapshot does not track the market closely enough")
    return 0 if got["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
