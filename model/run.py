"""Spec + snapshot in, Result out: the only place a Result is assembled.

Stdlib only. Validating the spec against `spec.schema.json` is the caller's job; the
engine refuses what it cannot run (an unregistered factor, a snapshot that does not
carry the spec's universe) and nothing else.
"""

from __future__ import annotations

import hashlib
import json

from . import audit
from .backtest import run_backtest
from .factors import factor
from .screen import sharia_at
from .snapshot import Snapshot

ENGINE_VERSION = "0.1.0"
SCHEMA_VERSION = "1.2"


def canonical(obj) -> str:
    """Canonical JSON for hashing. Equals RFC 8785 for the values a spec holds."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def spec_hash(spec: dict) -> str:
    return hashlib.sha256(canonical(spec).encode()).hexdigest()


def _families(spec: dict) -> list[str]:
    ids = [f["factor"] for f in spec["filters"]] + [r["factor"] for r in spec["rank"]]
    families = [factor(i).family for i in ids]
    if spec["sharia"] == "compliant_only":
        families.append("sharia")
    return families


def run(spec: dict, snap: Snapshot, query: str, generated_at: str) -> dict:
    if snap.universe != spec["universe"]:
        raise ValueError(f"snapshot carries {snap.universe!r}, spec asks for {spec['universe']!r}")
    families = _families(spec)  # raises on an unregistered factor, before any work
    bt = run_backtest(spec, snap)

    ids = [f["factor"] for f in spec["filters"]] + [r["factor"] for r in spec["rank"]]
    ranked = {s["symbol"]: s for s in bt["final_ranked"]}
    held = sorted(bt["final"], key=lambda s: (-ranked[s]["score"], s))
    rows = []
    for rank, symbol in enumerate(held, start=1):
        row = {
            "symbol": symbol,
            "name": snap.names.get(symbol, symbol),
            "rank": rank,
            "score": ranked[symbol]["score"],
            "factors": {i: ranked[symbol]["factors"][i] for i in dict.fromkeys(ids)},
            "sharia": sharia_at(snap, symbol, bt["as_of"])["status"],
            "weight": 1 / len(held),
        }
        if symbol in snap.sectors:
            row["sector"] = snap.sectors[symbol]
        rows.append(row)

    report = audit.grid_check(
        families,
        rank_exit=True,  # the spec cannot omit n_drop, so a holding always ends by rank
        curve=bt["curve"],
        bench=bt["bench"],
        turnover=bt["metrics"]["turnover"],
        max_weight=1 / spec["top_k"],
    )
    digest = spec_hash(spec)
    result = {
        "schema_version": SCHEMA_VERSION,
        "run_id": f"{digest[:12]}-{bt['as_of']}",
        "generated_at": generated_at,
        "as_of": bt["as_of"],
        "query": query,
        "spec": spec,
        "receipt": {"spec_hash": digest, "data_version": snap.version, "engine_version": ENGINE_VERSION},
        "rows": rows,
        "backtest": {
            "metrics": bt["metrics"],
            "equity_curve": [{"date": d, "value": v} for d, v in zip(bt["dates"], bt["curve"])],
        },
        "audit": {"grid": audit.grid_block(report)},
    }
    if len(held) < spec["top_k"]:
        result["warnings"] = [f"only {len(held)} of {spec['top_k']} names passed the screen on {bt['as_of']}"]
    return result
