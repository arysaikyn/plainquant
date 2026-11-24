"""Reproduce a Result from its receipt.

    python3 -m model.verify RESULT.json SNAPSHOT_DIR

Runs the spec stored in the Result on the snapshot and compares the two files, apart from
`generated_at`. Exit 0 means the same numbers; 1 means they differ; 2 means the snapshot is
not the one the receipt names.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import store
from .run import run


def differences(a, b, path: str = "") -> list[str]:
    """Paths where two JSON values differ."""
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append(f"{path}/{key}")
            else:
                out += differences(a[key], b[key], f"{path}/{key}")
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path} (length {len(a)} vs {len(b)})"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, f"{path}[{i}]")]
    return [] if a == b else [path or "/"]


def verify(result: dict, snap_dir: str) -> tuple[int, list[str]]:
    snap = store.load(snap_dir)
    if snap.version != result["receipt"]["data_version"]:
        return 2, [f"snapshot {snap.version} is not the receipt's {result['receipt']['data_version']}"]
    again = run(result["spec"], snap, result["query"], result["generated_at"])
    diff = differences(result, again)
    return (1 if diff else 0), diff


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m model.verify", description=__doc__.split("\n\n")[0])
    ap.add_argument("result")
    ap.add_argument("snapshot")
    args = ap.parse_args(argv)
    with open(args.result, encoding="utf-8") as fh:
        result = json.load(fh)
    code, diff = verify(result, args.snapshot)
    print({0: "same numbers", 1: "different numbers", 2: "wrong snapshot"}[code])
    for line in diff[:20]:
        print("  ", line)
    return code


if __name__ == "__main__":
    sys.exit(main())
