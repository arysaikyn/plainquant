"""Question -> Spec, with the language model on the far side of a function call.

`complete(messages) -> str` is the only thing this module knows about a model, so the
boundary is testable with a scripted one and no provider is baked in. The model writes
a spec or refuses; this module extracts it, validates it against `spec.schema.json`
and the factor registry, and gives the model a bounded number of tries to fix what it
got wrong. A spec that never validates is returned as a failure, never as a guess.

Needs `jsonschema` at runtime: it is the reference validator of the contract, and the
model's output is untrusted input.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from model.factors import REGISTRY

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None

Complete = Callable[[list[dict]], str]

SPEC_SCHEMA_TEXT = (Path(__file__).resolve().parent.parent / "model" / "spec.schema.json").read_text(encoding="utf-8")
SPEC_SCHEMA = json.loads(SPEC_SCHEMA_TEXT)

# The one Python owner of "what a spec means when the question is silent".
DEFAULTS = {"rebalance": "M", "n_drop": 2, "top_k": 10, "fee_rate": 0.0015, "slip_rate": 0.005, "years": 5}
REFUSALS = ("execution", "guarantee", "advice")  # the product boundary, as lib/refusal.ts names it
MAX_REPAIRS = 2


def system_prompt(universes: dict[str, str], today: str) -> str:
    refusals = ", ".join(json.dumps({"refuse": rule}) for rule in REFUSALS)
    factors = "\n".join(f"- {f.id} ({f.family})" for f in REGISTRY.values())
    return f"""You turn a retail investor's question into a strategy spec. Reply with one JSON object and nothing else.

The spec must satisfy this JSON Schema exactly. It is closed: add no field it does not list.
{SPEC_SCHEMA_TEXT}

Factors you may use, by id (no other id exists):
{factors}

Universes available, with their market: {", ".join(f"{u} (market {m})" for u, m in universes.items())}. Pick one as "universe" and use its market as "market".

When the question is silent, use: rebalance {DEFAULTS["rebalance"]}, n_drop {DEFAULTS["n_drop"]}, top_k {DEFAULTS["top_k"]}, \
costs fee_rate {DEFAULTS["fee_rate"]} and slip_rate {DEFAULTS["slip_rate"]}, and a period of the {DEFAULTS["years"]} years ending {today}. \
"sharia" is "compliant_only" only if the question asks for it.

A holding ends by leaving the ranking. There is no stop-loss, take-profit or entry price in this product; do not invent one.
If the question asks you to place an order, promises a guaranteed result, or asks what to buy or sell, do not write a spec. \
Reply with one of: {refusals}."""


def extract_json(text: str) -> dict | None:
    """The first balanced top-level object in `text`, tolerant of prose and code fences."""
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start : i + 1])
                    except ValueError:
                        break
                    return value if isinstance(value, dict) else None
        start = text.find("{", start + 1)
    return None


def problems(spec: dict, universes: dict[str, str] | None = None) -> list[str]:
    """Why `spec` cannot be run, as short lines a model can act on. Empty means it can."""
    if Draft202012Validator is None:
        raise ImportError("agent.spec needs jsonschema to validate a model's output")
    out = [
        f"{'.'.join(str(p) for p in e.absolute_path) or 'spec'}: {e.message[:160]}"
        for e in sorted(Draft202012Validator(SPEC_SCHEMA).iter_errors(spec), key=lambda e: [str(p) for p in e.absolute_path])
    ]
    if not out:
        for where, items in (("filters", spec["filters"]), ("rank", spec["rank"])):
            for i, item in enumerate(items):
                if item["factor"] not in REGISTRY:
                    out.append(f"{where}[{i}].factor: {item['factor']!r} is not a factor; use one of {sorted(REGISTRY)}")
        if universes is not None and universes.get(spec["universe"]) != spec["market"]:
            out.append(f"universe: {spec['universe']!r} with market {spec['market']!r} is not available; use one of {universes}")
    return out


@dataclass
class Outcome:
    spec: dict | None = None
    refusal: str | None = None
    problems: list[str] = field(default_factory=list)
    attempts: int = 0

    @property
    def ok(self) -> bool:
        return self.spec is not None


def question_to_spec(
    question: str, complete: Complete, universes: dict[str, str], today: str, max_repairs: int = MAX_REPAIRS
) -> Outcome:
    messages = [
        {"role": "system", "content": system_prompt(universes, today)},
        {"role": "user", "content": question},
    ]
    outcome = Outcome()
    for _ in range(1 + max_repairs):
        outcome.attempts += 1
        reply = complete(messages)
        doc = extract_json(reply)
        if doc is None:
            outcome.problems = ["the reply held no JSON object"]
        elif set(doc) == {"refuse"} and doc["refuse"] in REFUSALS:
            return Outcome(refusal=doc["refuse"], attempts=outcome.attempts)
        else:
            outcome.problems = problems(doc, universes)
            if not outcome.problems:
                outcome.spec, outcome.problems = doc, []
                return outcome
        messages += [
            {"role": "assistant", "content": reply},
            {
                "role": "user",
                "content": "That is not a valid spec:\n- " + "\n- ".join(outcome.problems[:8]) + "\nReply with the corrected JSON object only.",
            },
        ]
    return outcome
