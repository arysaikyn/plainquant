"""Read and write a snapshot as a directory of CSV files plus a manifest.

The format is the contract between a data adapter and the engine; the adapter that
fills it for a given vendor lives outside model/. Raw data stays out of git: put
snapshot directories under `data/raw/`.

    manifest.json   {"format": 2, "universe": ..., "market": ..., "files": {name: sha256}}
    dates.csv       date
    prices.csv      symbol,date,close
    facts.csv       symbol,announce_date,key,value        (empty value = not published)
    membership.csv  symbol,first,last                     (empty last = still a member)
    names.csv       symbol,name,sector

`data_version` is a hash of the manifest, so it changes if and only if a byte of data
does. A fact row without an announcement date is refused: without it the row cannot be
placed in time, and an engine that guessed would be reading the future.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from .run import canonical
from .snapshot import Snapshot

FORMAT = 2
FILES = ("dates.csv", "prices.csv", "facts.csv", "membership.csv", "names.csv")


def _num(text: str) -> float | None:
    return float(text) if text != "" else None


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows([["" if v is None else v for v in row] for row in rows])


def version_of(manifest: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical(manifest).encode()).hexdigest()


def write(snap: Snapshot, directory: str | Path) -> str:
    """Write `snap` and return its data_version."""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    _write(out / "dates.csv", ["date"], [[d] for d in snap.dates])
    _write(
        out / "prices.csv",
        ["symbol", "date", "close"],
        [[s, d, repr(p)] for s in sorted(snap.prices) for d, p in sorted(snap.prices[s].items())],
    )
    _write(
        out / "facts.csv",
        ["symbol", "announce_date", "key", "value"],
        [
            [s, d, k, None if v is None else repr(v)]
            for s in sorted(snap.facts)
            for d, row in snap.facts[s]
            for k, v in sorted(row.items())
        ],
    )
    _write(
        out / "membership.csv",
        ["symbol", "first", "last"],
        [[s, first, last] for s, (first, last) in sorted(snap.membership.items())],
    )
    _write(
        out / "names.csv",
        ["symbol", "name", "sector"],
        [[s, snap.names.get(s, s), snap.sectors.get(s)] for s in sorted(snap.membership)],
    )
    manifest = {
        "format": FORMAT,
        "universe": snap.universe,
        "market": snap.market,
        "files": {f: hashlib.sha256((out / f).read_bytes()).hexdigest() for f in FILES},
    }
    (out / "manifest.json").write_text(canonical(manifest) + "\n", encoding="utf-8")
    return version_of(manifest)


def _rows(path: Path):
    with path.open(newline="", encoding="utf-8") as fh:
        yield from csv.DictReader(fh)


def load(directory: str | Path) -> Snapshot:
    src = Path(directory)
    manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT:
        raise ValueError(f"unsupported snapshot format {manifest.get('format')!r}")
    for name in FILES:
        expected = manifest["files"].get(name)
        actual = hashlib.sha256((src / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"{name} does not match the manifest; the snapshot was changed after it was written")

    dates = [r["date"] for r in _rows(src / "dates.csv")]
    if dates != sorted(set(dates)):
        raise ValueError("dates.csv must be ascending and unique")

    prices: dict[str, dict[str, float]] = {}
    for r in _rows(src / "prices.csv"):
        close = _num(r["close"])
        if close is None or close <= 0:
            raise ValueError(f"non-positive close for {r['symbol']} on {r['date']}")
        prices.setdefault(r["symbol"], {})[r["date"]] = close

    grouped: dict[str, dict[str, dict[str, float | None]]] = {}
    for r in _rows(src / "facts.csv"):
        if not r["announce_date"]:
            raise ValueError(f"fact {r['symbol']}/{r['key']} has no announcement date")
        grouped.setdefault(r["symbol"], {}).setdefault(r["announce_date"], {})[r["key"]] = _num(r["value"])
    facts = {s: sorted(by_date.items()) for s, by_date in grouped.items()}

    membership = {r["symbol"]: (r["first"], r["last"] or None) for r in _rows(src / "membership.csv")}
    names_rows = list(_rows(src / "names.csv"))
    return Snapshot(
        version=version_of(manifest),
        universe=manifest["universe"],
        market=manifest["market"],
        dates=dates,
        prices=prices,
        facts=facts,
        membership=membership,
        names={r["symbol"]: r["name"] for r in names_rows},
        sectors={r["symbol"]: r["sector"] for r in names_rows if r["sector"]},
    )
