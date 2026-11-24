"""Fill a point-in-time snapshot from Baostock (www.baostock.com), a free A-share service.

    python3 -m data.baostock_source --out data/raw/csi300 --start 2019-01-01 --end 2024-12-31

Needs the `baostock` package, which is not a dependency of this repo: install it yourself,
or point PYTHONPATH at a copy you have read. Raw output stays under `data/raw/`, which git
ignores. Whether this data may be shown or redistributed is NOT confirmed (see
docs/product.md, open question 1); use it for local research only.

The field names this module reads were checked against a live response on 2026-11-23
(balance: pubDate, assetToEquity, liabilityToAsset; dividend: dividPlanAnnounceDate,
dividCashPsBeforeTax; industry; k data: date, close, tradestatus). Every read goes through
`need()`, which names the fields the server really sent when one is missing.

The live response showed a defect that no fake could: in newer reports `liabilityToAsset`
is 100 times too small (sh.600000, sh.600519 and sh.601398 in the 2024 reports), while
`assetToEquity` is right. So debt_ratio is derived as 1 - 1/assetToEquity, and the source's
own `liabilityToAsset` is only a cross-check whose disagreements are counted.

What the engine reads from here is point in time: a financial report becomes visible on its
publication date, never its period end. The defects that cannot be fixed with this source
are written into the snapshot as `limitations`, and every Result run on it repeats them.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from bisect import bisect_right
from datetime import date, timedelta

from model import store
from model.snapshot import Snapshot

LIMITATIONS = [
    "Membership is the CSI 300 list the source gives on the first day of each half year, kept until the next sample. A change made in between shows up late, and an interim removal (a delisting) is not seen until the next sample.",
    "A name that was delisted keeps its last price, so no loss after its last trade is recorded.",
    "debt_ratio is total liabilities over total assets. The balance endpoint of this source carries only ratios: interest-bearing debt, deposits, interest income and receivables are not published, so every name is Sharia unknown and compliant_only returns nothing.",
    "dividend_yield is the cash dividend announced in the last 365 days over the unadjusted close on the day of the latest announcement; it does not move with the price in between. A name with no announcement in the window reads 0.",
    "Prices are back-adjusted closes (dividends reinvested); suspended days are absent and carry the last price.",
]


class Quality:
    """What the builder saw in the source's own data; reported in the snapshot's limitations."""

    def __init__(self) -> None:
        self.reports = 0  # balance reports used
        self.disagreements = 0  # liabilityToAsset differed from 1 - 1/assetToEquity by more than 0.02
        self.skipped = 0  # reports without a usable assetToEquity

    def sentence(self) -> str | None:
        if not self.reports and not self.skipped:
            return None
        return (
            f"debt_ratio is 1 - 1/assetToEquity. The source's liabilityToAsset disagreed with it in "
            f"{self.disagreements} of {self.reports} reports (it is scaled 100 times too small in newer ones), "
            f"and {self.skipped} reports had no usable assetToEquity and were dropped."
        )


class SourceError(RuntimeError):
    pass


def query(rs, what: str) -> list[dict]:
    """Every row of a Baostock result set as a dict; raises with the server's own message."""
    if rs.error_code != "0":
        raise SourceError(f"baostock {what}: {rs.error_code} {rs.error_msg}")
    rows = []
    while rs.next():
        rows.append(dict(zip(rs.fields, rs.get_row_data())))
    return rows


def need(row: dict, field: str, what: str):
    """`row[field]`, or an error that lists the fields the server really sent."""
    if field not in row:
        raise SourceError(f"baostock {what}: no field {field!r}; the server sent {sorted(row)}")
    return row[field]


def symbol(code: str) -> str:
    """`sh.600036` -> `600036.SH`, the form the contract's example uses."""
    exchange, number = code.split(".")
    return f"{number}.{exchange.upper()}"


def _number(text: str) -> float | None:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if value == value else None  # NaN is not a number


def closes(bs, code: str, start: str, end: str, adjust: str) -> dict[str, float]:
    """Close by date for the days the stock traded. `adjust` 1 is back-adjusted, 3 is raw."""
    rows = query(
        bs.query_history_k_data_plus(
            code, "date,close,tradestatus", start_date=start, end_date=end, frequency="d", adjustflag=adjust
        ),
        f"k data {code}",
    )
    out: dict[str, float] = {}
    for row in rows:
        price = _number(need(row, "close", "k data"))
        if need(row, "tradestatus", "k data") == "1" and price is not None and price > 0:
            out[need(row, "date", "k data")] = price
    return out


def debt_reports(bs, code: str, years: range, quality: Quality) -> list[tuple[str, float]]:
    """(publication date, liabilities over assets) for every report in `years`.

    The ratio is 1 - 1/assetToEquity; see the module note on why liabilityToAsset is not used.
    Two reports can be published on one day (the annual report and the first quarter, in
    late April); the one for the later period comes last, so it is the one in force.
    """
    out = []
    for year in years:
        for quarter in (1, 2, 3, 4):
            for row in query(bs.query_balance_data(code=code, year=year, quarter=quarter), f"balance {code}"):
                published = need(row, "pubDate", "balance")
                multiplier = _number(need(row, "assetToEquity", "balance"))
                stated = _number(need(row, "liabilityToAsset", "balance"))
                if not published:
                    continue
                if multiplier is None or multiplier <= 1:
                    quality.skipped += 1
                    continue
                ratio = 1 - 1 / multiplier
                quality.reports += 1
                if stated is not None and abs(stated - ratio) > 0.02:
                    quality.disagreements += 1
                out.append((published, need(row, "statDate", "balance"), ratio))
    return [(published, ratio) for published, _, ratio in sorted(out)]


def dividend_announcements(bs, code: str, years: range) -> list[tuple[str, float]]:
    """(announcement date, cash dividend per share before tax)."""
    out = []
    for year in years:
        for row in query(bs.query_dividend_data(code=code, year=str(year), yearType="report"), f"dividend {code}"):
            announced = need(row, "dividPlanAnnounceDate", "dividend")
            cash = _number(need(row, "dividCashPsBeforeTax", "dividend"))
            if announced and cash is not None:
                out.append((announced, cash))
    return sorted(out)


def fact_rows(
    debts: list[tuple[str, float]], dividends: list[tuple[str, float]], raw: dict[str, float]
) -> list[tuple[str, dict[str, float | None]]]:
    """One row per date something was announced, each carrying everything known on that date.

    The engine reads the latest row only, so a dividend announcement must repeat the last
    debt ratio, and the other way round; leaving a key out would make the name unrankable.
    """
    raw_dates = sorted(raw)
    out: list[tuple[str, dict[str, float | None]]] = []
    debt: float | None = None
    for day in sorted({d for d, _ in debts} | {d for d, _ in dividends}):
        for published, ratio in debts:
            if published == day:
                debt = ratio
        row: dict[str, float | None] = {}
        if debt is not None:
            row["debt_ratio"] = debt
        i = bisect_right(raw_dates, day)
        if i:
            since = (date.fromisoformat(day) - timedelta(days=365)).isoformat()
            paid = sum(c for d, c in dividends if since < d <= day)
            row["dividend_yield"] = paid / raw[raw_dates[i - 1]]
        if row:
            out.append((day, row))
    return out


def sample_days(start: str, end: str) -> list[str]:
    """`start`, then the first day of each half year up to `end`."""
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    days = {start}
    for year in range(first.year, last.year + 1):
        for month in (1, 7):
            day = date(year, month, 1)
            if first < day <= last:
                days.add(day.isoformat())
    return sorted(days)


def membership_intervals(lists: list[tuple[str, set[str]]]) -> dict[str, list[tuple[str, str | None]]]:
    """From the member lists sampled on ascending days: when each code was in the index.

    A code is a member from the first sample that lists it until the day before the first
    later sample that does not; it can leave and come back. Still listed at the end: no end.
    """
    out: dict[str, list[tuple[str, str | None]]] = {}
    since: dict[str, str] = {}
    for day, codes in lists:
        for code in sorted(codes - since.keys()):
            since[code] = day
        for code in sorted(set(since) - codes):
            before = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
            out.setdefault(code, []).append((since.pop(code), before))
    for code, first in since.items():
        out.setdefault(code, []).append((first, None))
    return out


TRIES = 3


def fetch_name(bs, code: str, start: str, end: str, years: range, quality: Quality):
    """Everything one name needs, retried: a long run must not die on one dropped connection.
    The quality counts of a failed try are discarded, so a retry does not count twice."""
    last: Exception | None = None
    for attempt in range(TRIES):
        trial = Quality()
        try:
            adjusted = closes(bs, code, start, end, "1")
            if not adjusted:
                return None
            raw = closes(bs, code, f"{years.start}-01-01", end, "3")
            debts = debt_reports(bs, code, years, trial)
            dividends = dividend_announcements(bs, code, years)
            sector = next((r["industry"] for r in query(bs.query_stock_industry(code=code), f"industry {code}") if r.get("industry")), None)
        except SourceError as exc:
            last = exc
            bs.logout()
            bs.login()  # a dropped session answers every later query with an error
            continue
        quality.reports += trial.reports
        quality.disagreements += trial.disagreements
        quality.skipped += trial.skipped
        return adjusted, fact_rows(debts, dividends, raw), sector
    raise SourceError(f"{code}: {TRIES} tries failed, last: {last}")


def _load_cached(path: Path):
    """One name saved by `_save`, or None when it was never fetched."""
    if not path.exists():
        return None
    got = json.loads(path.read_text(encoding="utf-8"))
    rows = [(day, row) for day, row in got["rows"]]
    return got["adjusted"], rows, got["sector"], got["quality"]


def _save(path: Path, adjusted, rows, sector, quality: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"adjusted": adjusted, "rows": rows, "sector": sector, "quality": quality}), encoding="utf-8")
    tmp.replace(path)  # a kill mid-write leaves no half file under the final name


def build(
    bs,
    start: str,
    end: str,
    limit: int | None = None,
    log=lambda text: None,
    cache: Path | None = None,
    pause=time.sleep,
) -> Snapshot:
    """`cache` is a directory that holds one file per fetched name. A run that dies resumes
    from it: a name already there is not asked for again. Names that failed are retried once
    more at the end, after a pause."""
    first, last = date.fromisoformat(start).year, date.fromisoformat(end).year
    years = range(first - 1, last + 1)  # the report published before `start` still matters

    lists: list[tuple[str, set[str]]] = []
    called: dict[str, str] = {}  # code -> name, in order of first appearance
    for day in sample_days(start, end):
        rows = query(bs.query_hs300_stocks(date=day), f"hs300 {day}")
        members = {need(r, "code", "hs300"): need(r, "code_name", "hs300") for r in rows}
        lists.append((day, set(members)))
        for code, name in members.items():
            called.setdefault(code, name)
        log(f"members on {day}: {len(members)}")
    intervals = membership_intervals(lists)
    pairs = list(called.items())[:limit]
    quality = Quality()

    prices: dict[str, dict[str, float]] = {}
    facts: dict[str, list] = {}
    names: dict[str, str] = {}
    sectors: dict[str, str] = {}
    failed: list[tuple[str, str]] = []

    def take(code: str, name: str, got, label: str) -> None:
        adjusted, rows, sector = got
        sym = symbol(code)
        prices[sym], names[sym], facts[sym] = adjusted, name, rows
        if sector:
            sectors[sym] = sector
        log(f"{label} {sym} {len(adjusted)} days, {len(rows)} fact rows")

    def fetch(code: str, name: str, label: str) -> bool:
        path = cache / f"{code}.json" if cache else None
        saved = _load_cached(path) if path else None
        if saved:
            adjusted, rows, sector, counts = saved
            quality.reports += counts["reports"]
            quality.disagreements += counts["disagreements"]
            quality.skipped += counts["skipped"]
            take(code, name, (adjusted, rows, sector), f"{label} cached")
            return True
        one = Quality()
        try:
            got = fetch_name(bs, code, start, end, years, one)
        except SourceError as exc:
            log(f"FAILED {code}: {exc}")
            return False
        if got is None:
            log(f"skip {code}: no traded days in the window")
            return True
        counts = {"reports": one.reports, "disagreements": one.disagreements, "skipped": one.skipped}
        quality.reports += one.reports
        quality.disagreements += one.disagreements
        quality.skipped += one.skipped
        if path:
            _save(path, got[0], got[1], got[2], counts)
        take(code, name, got, label)
        return True

    for n, (code, name) in enumerate(pairs, start=1):
        if not fetch(code, name, f"{n}/{len(pairs)}"):
            failed.append((code, name))
    if failed:
        log(f"{len(failed)} names failed; retrying them once after a pause")
        pause(60)
        bs.logout()
        bs.login()
        failed = [(c, n) for c, n in failed if not fetch(c, n, "retry")]
    failed_codes = [c for c, _ in failed]

    return Snapshot(
        version="",
        universe="csi300",
        market="cn_a",
        dates=sorted({d for series in prices.values() for d in series}),
        prices=prices,
        facts=facts,
        membership={symbol(code): intervals[code] for code, _ in pairs if symbol(code) in prices},
        names=names,
        sectors=sectors,
        limitations=LIMITATIONS
        + ([quality.sentence()] if quality.sentence() else [])
        + ([f"{len(failed_codes)} names could not be fetched after {TRIES} tries, twice, and are missing: {', '.join(failed_codes)}."] if failed_codes else []),
    )


def main(argv: list[str] | None = None, bs=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m data.baostock_source", description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, help="snapshot directory to write (use data/raw/...)")
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2024-12-31")
    ap.add_argument("--cache", help="directory for one file per fetched name; a rerun with the same directory resumes (default: OUT.partial)")
    ap.add_argument("--limit", type=int, help="fetch only the first N constituents (a quick trial)")
    args = ap.parse_args(argv)
    if bs is None:
        import baostock as bs  # not a dependency of this repo; see the module doc
    login = bs.login()
    if login.error_code != "0":
        print(f"data: login failed: {login.error_code} {login.error_msg}", file=sys.stderr)
        return 2
    try:
        cache = Path(args.cache or f"{args.out.rstrip('/')}.partial")
        stamp = lambda text: print(f"{datetime.now():%H:%M:%S} {text}", file=sys.stderr, flush=True)  # noqa: E731
        snap = build(bs, args.start, args.end, args.limit, log=stamp, cache=cache)
    except SourceError as exc:
        print(f"data: {exc}", file=sys.stderr)
        return 2
    finally:
        bs.logout()
    print(f"data: wrote {len(snap.prices)} names, {len(snap.dates)} dates -> {store.write(snap, args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
