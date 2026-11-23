"""Score a model against a fixed set of questions.

The measurement the agent layer must move: how often a question becomes a valid spec,
and how often that spec says what the question asked. Cases live in
`agent/evals/spec_cases.json`; `expect` is a subset the spec must contain (lists match
as sets), `refuse` is the refusal the question must get. Run it with any `complete`
function, so a model change is a number before it is an opinion.
"""

from __future__ import annotations

import json
from pathlib import Path

from .spec import Complete, question_to_spec

CASES = Path(__file__).resolve().parent / "evals" / "spec_cases.json"


def contains(expected, actual) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and contains(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and all(any(contains(e, a) for a in actual) for e in expected)
    return expected == actual


def evaluate(cases: list[dict], complete: Complete, universes: dict[str, str], today: str) -> dict:
    asked = [c for c in cases if "expect" in c]
    refused = [c for c in cases if "refuse" in c]
    failures: list[dict] = []
    valid = correct = right_refusals = 0
    for case in asked:
        out = question_to_spec(case["question"], complete, universes, today)
        valid += out.ok
        if out.ok and contains(case["expect"], out.spec):
            correct += 1
        else:
            failures.append({"question": case["question"], "problems": out.problems, "refusal": out.refusal})
    for case in refused:
        out = question_to_spec(case["question"], complete, universes, today)
        if out.refusal == case["refuse"]:
            right_refusals += 1
        else:
            failures.append({"question": case["question"], "got_spec": out.ok, "refusal": out.refusal})
    return {
        "specs": len(asked),
        "valid": valid,
        "correct": correct,
        "refusals": len(refused),
        "refusals_correct": right_refusals,
        "failures": failures,
    }


def load_cases(path: Path = CASES) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))
