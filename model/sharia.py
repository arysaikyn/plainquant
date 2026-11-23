"""The Sharia screen: a filter that runs before ranking.

Port of web/src/data/shariaCoverage.ts. Three outcomes, in the vocabulary of the
Result contract. A missing input outranks a breach: the name is unproven, not
condemned, and unknown is not compliant. The AAOIFI caps live here and nowhere else
in model/; the copy in web/ goes when web/ reads this engine's output.
"""

from __future__ import annotations

import math
from collections.abc import Callable

# field -> (fact key the snapshot carries, cap as a fraction)
FIELDS = {
    "debt": ("debt_ratio", 0.3),
    "interest_bearing": ("interest_bearing_ratio", 0.3),
    "income": ("impure_income_ratio", 0.05),
    "receivables": ("receivables_ratio", 0.3333),
}


def verdict(read: Callable[[str], float | None]) -> dict:
    """`read(fact_key)` returns the point-in-time value, or None if unpublished."""
    values: dict[str, float | None] = {}
    for field, (key, _) in FIELDS.items():
        value = read(key)
        values[field] = None if value is None or not math.isfinite(value) else value
    missing = [f for f, v in values.items() if v is None]
    failed = [
        {"field": f, "value": v, "limit": FIELDS[f][1]}
        for f, v in values.items()
        if v is not None and v > FIELDS[f][1]
    ]
    if missing:
        status = "unknown"
    elif failed:
        status = "non_compliant"
    else:
        status = "compliant"
    return {"status": status, "values": values, "failed": failed, "missing": missing}
