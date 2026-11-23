"""Run a spec on a snapshot and write the Result.

    python3 -m model SPEC.json SNAPSHOT_DIR --query "..." [-o model/signals.json]

`model/signals.json` is the file the web contract names; it is generated per run and
gitignored. Without `-o` the Result goes to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from . import store
from .run import canonical, run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m model", description=__doc__.split("\n\n")[0])
    ap.add_argument("spec", help="path to a spec JSON file")
    ap.add_argument("snapshot", help="snapshot directory (see model/store.py)")
    ap.add_argument("--query", required=True, help="the question the spec answers, kept in the Result")
    ap.add_argument("-o", "--out", help="write here instead of stdout")
    ap.add_argument("--generated-at", help="ISO timestamp; defaults to now (UTC). Fix it for a reproducible file.")
    args = ap.parse_args(argv)

    with open(args.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    stamp = args.generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        result = run(spec, store.load(args.snapshot), args.query, stamp)
    except (ValueError, KeyError) as exc:
        print(f"model: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
