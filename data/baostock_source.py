"""Fill a point-in-time snapshot from Baostock (www.baostock.com), a free A-share service.

    python3 -m data.baostock_source --out data/raw/csi300 --start 2019-01-01 --end 2024-12-31

Needs the `baostock` package, which is not a dependency of this repo: install it yourself,
or point PYTHONPATH at a copy you have read. Raw output stays under `data/raw/`, which git
ignores. Whether this data may be shown or redistributed is NOT confirmed (see
docs/product.md, open question 1); use it for local research only.

The field names this module reads (liabilityToAsset, pubDate, dividPlanAnnounceDate,
dividCashPsBeforeTax, industry) come from Baostock's documentation, not from its code, and
have not been checked against a live response. Every read goes through `need()`, which
names the fields the server really sent when one is missing, so the first real run says what
to fix instead of writing a wrong snapshot.

What the engine reads from here is point in time: a financial report becomes visible on its
publication date, never its period end. The defects that cannot be fixed with this source
are written into the snapshot as `limitations`, and every Result run on it repeats them.
"""

from __future__ import annotations

import argparse
import sys
from bisect import bisect_right
from datetime import date, timedelta

from model import store
from model.snapshot import Snapshot

LIMITATIONS = [
    "The universe is today's CSI 300 list, not the index as it stood on each date; names that left it are missing, which flatters the results (survivorship bias).",
    "debt_ratio is total liabilities over total assets. The AAOIFI inputs are not published by this source, so every name is Sharia unknown and compliant_only returns nothing.",
    "dividend_yield is the cash dividend announced in the last 365 days over the unadjusted close on the day of the latest announcement; it does not move with the price in between. A name with no announcement in the window reads 0.",
    "Prices are back-adjusted closes (dividends reinvested); suspended days are absent and carry the last price.",
]


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


def debt_reports(bs, code: str, years: range) -> list[tuple[str, float]]:
    """(publication date, liabilities over assets) for every report in `years`."""
    out = []
    for year in years:
        for quarter in (1, 2, 3, 4):
            for row in query(bs.query_balance_data(code=code, year=year, quarter=quarter), f"balance {code}"):
                published = need(row, "pubDate", "balance")
                ratio = _number(need(row, "liabilityToAsset", "balance"))
                if published and ratio is not None:
                    out.append((published, ratio))
    return sorted(out)


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


def build(bs, start: str, end: str, limit: int | None = None, log=lambda text: None) -> Snapshot:
    first, last = date.fromisoformat(start).year, date.fromisoformat(end).year
    years = range(first - 1, last + 1)  # the report published before `start` still matters
    constituents = query(bs.query_hs300_stocks(), "hs300")
    pairs = [(need(r, "code", "hs300"), need(r, "code_name", "hs300")) for r in constituents][:limit]

    prices: dict[str, dict[str, float]] = {}
    facts: dict[str, list] = {}
    names: dict[str, str] = {}
    sectors: dict[str, str] = {}
    for n, (code, name) in enumerate(pairs, start=1):
        adjusted = closes(bs, code, start, end, "1")
        if not adjusted:
            log(f"skip {code}: no traded days in the window")
            continue
        sym = symbol(code)
        prices[sym], names[sym] = adjusted, name
        raw = closes(bs, code, f"{first - 1}-01-01", end, "3")
        facts[sym] = fact_rows(debt_reports(bs, code, years), dividend_announcements(bs, code, years), raw)
        for row in query(bs.query_stock_industry(code=code), f"industry {code}"):
            if row.get("industry"):
                sectors[sym] = row["industry"]
        log(f"{n}/{len(pairs)} {sym} {len(adjusted)} days, {len(facts[sym])} fact rows")

    return Snapshot(
        version="",
        universe="csi300",
        market="cn_a",
        dates=sorted({d for series in prices.values() for d in series}),
        prices=prices,
        facts=facts,
        membership={sym: (start, None) for sym in prices},
        names=names,
        sectors=sectors,
        limitations=list(LIMITATIONS),
    )


def main(argv: list[str] | None = None, bs=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m data.baostock_source", description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, help="snapshot directory to write (use data/raw/...)")
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2024-12-31")
    ap.add_argument("--limit", type=int, help="fetch only the first N constituents (a quick trial)")
    args = ap.parse_args(argv)
    if bs is None:
        import baostock as bs  # not a dependency of this repo; see the module doc
    login = bs.login()
    if login.error_code != "0":
        print(f"data: login failed: {login.error_code} {login.error_msg}", file=sys.stderr)
        return 2
    try:
        snap = build(bs, args.start, args.end, args.limit, log=lambda text: print(text, file=sys.stderr))
    except SourceError as exc:
        print(f"data: {exc}", file=sys.stderr)
        return 2
    finally:
        bs.logout()
    print(f"data: wrote {len(snap.prices)} names, {len(snap.dates)} dates -> {store.write(snap, args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
