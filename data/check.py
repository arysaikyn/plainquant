"""Is this snapshot fit to run on? Checks a snapshot directory and prints what it finds.

    python3 -m data.check data/raw/csi300

Exit 0 when there is no error, 1 when there is one, 2 when the snapshot does not load.
An error means the numbers cannot be trusted as they stand; a warning means a limit the
reader should know. Every threshold is a constant below, so a change is a diff.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from dataclasses import dataclass
from datetime import date

from model import store
from model.snapshot import Snapshot

CALENDAR_GAP_DAYS = 14  # measured: the longest real closures in 2019-2024 were 11 days (Spring Festival 2020 and 2024)
JUMP = 0.25  # a one-day move of a back-adjusted close beyond this is suspect (20% is the widest daily limit)
YIELD_CEILING = 0.20
LATE_NAME_SHARE = 0.5  # a name with prices on under half of the dates
MEMBER_FLOOR = 0.8  # tradable members on a date, as a share of the median
DELISTED_AFTER_DAYS = 30


@dataclass
class Finding:
    level: str  # "error" | "warn" | "info"
    what: str
    detail: str

    def __str__(self) -> str:
        return f"{self.level.upper():5} {self.what}: {self.detail}"


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def check(snap: Snapshot) -> list[Finding]:
    out: list[Finding] = []
    n_dates = len(snap.dates)

    gaps = [(a, b) for a, b in zip(snap.dates, snap.dates[1:]) if _days(a, b) > CALENDAR_GAP_DAYS]
    out.append(Finding("error" if gaps else "info", "calendar", f"{n_dates} trading days, {snap.dates[0]} to {snap.dates[-1]}; "
        + (f"{len(gaps)} gaps over {CALENDAR_GAP_DAYS} days, first {gaps[0][0]} to {gaps[0][1]}" if gaps else "no gap over " + str(CALENDAR_GAP_DAYS) + " days")))

    jumps = []
    for sym, series in snap.prices.items():
        days = sorted(series)
        for a, b in zip(days, days[1:]):
            move = series[b] / series[a] - 1
            if abs(move) > JUMP:
                jumps.append((abs(move), sym, b, move))
    jumps.sort(reverse=True)
    out.append(Finding("warn" if jumps else "info", "price jumps", f"{len(jumps)} one-day moves beyond {JUMP:.0%} in adjusted closes"
        + (f"; largest {jumps[0][1]} on {jumps[0][2]} ({jumps[0][3]:+.0%})" if jumps else "")))

    late = sorted(s for s, series in snap.prices.items() if len(series) < LATE_NAME_SHARE * n_dates)
    out.append(Finding("info", "short histories", f"{len(late)} names have prices on under {LATE_NAME_SHARE:.0%} of the dates"
        + (f" (listed or delisted inside the window): {', '.join(late[:6])}" + (" ..." if len(late) > 6 else "") if late else "")))

    ended = sorted(s for s, series in snap.prices.items() if _days(max(series), snap.dates[-1]) > DELISTED_AFTER_DAYS)
    out.append(Finding("warn" if ended else "info", "ended series", f"{len(ended)} names stop trading more than {DELISTED_AFTER_DAYS} days before the end"
        + ("; each keeps its last price afterwards: " + ", ".join(ended[:6]) if ended else "")))

    no_facts = sorted(s for s in snap.prices if not snap.facts.get(s))
    out.append(Finding("error" if no_facts else "info", "reports", f"{len(no_facts)} names have no report at all" + (f": {', '.join(no_facts[:6])}" if no_facts else "")))
    bad_debt = [(s, d, r["debt_ratio"]) for s, rows in snap.facts.items() for d, r in rows if "debt_ratio" in r and not 0 < r["debt_ratio"] < 1]
    out.append(Finding("error" if bad_debt else "info", "debt_ratio", f"{len(bad_debt)} values outside (0, 1)" + (f"; first {bad_debt[0]}" if bad_debt else "")))
    rich = [(s, d, r["dividend_yield"]) for s, rows in snap.facts.items() for d, r in rows if r.get("dividend_yield", 0) > YIELD_CEILING]
    out.append(Finding("warn" if rich else "info", "dividend_yield", f"{len(rich)} values above {YIELD_CEILING:.0%}" + (f"; first {rich[0]}" if rich else "")))
    unranked = [s for s in snap.prices if snap.facts.get(s) and min(snap.facts[s])[0] > min(snap.prices[s])]
    out.append(Finding("info", "early gap", f"{len(unranked)} names trade before their first published report; they cannot be ranked on a report until it appears"))

    # Members that can be traded, sampled on the first trading day of each month.
    firsts, last_month = [], None
    for d in snap.dates:
        if d[:7] != last_month:
            firsts.append(d)
            last_month = d[:7]
    sizes = [sum(1 for s in snap.universe_at(d) if d in snap.prices.get(s, {})) for d in firsts]
    median = statistics.median(sizes)
    thin = [(d, n) for d, n in zip(firsts, sizes) if n < MEMBER_FLOOR * median]
    out.append(Finding("warn" if thin else "info", "members", f"tradable members per month: min {min(sizes)}, median {median:g}, max {max(sizes)}"
        + (f"; {len(thin)} months under {MEMBER_FLOOR:.0%} of the median, first {thin[0]}" if thin else "")))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m data.check", description=__doc__.split("\n\n")[0])
    ap.add_argument("snapshot", help="snapshot directory")
    args = ap.parse_args(argv)
    try:
        snap = store.load(args.snapshot)
    except (ValueError, OSError, KeyError) as exc:
        print(f"data: cannot load {args.snapshot}: {exc}", file=sys.stderr)
        return 2
    print(f"{snap.market} {snap.universe}, {len(snap.prices)} names, data_version {snap.version[:23]}...")
    findings = check(snap)
    for f in findings:
        print(f)
    return 1 if any(f.level == "error" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
