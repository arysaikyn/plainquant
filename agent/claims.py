"""Result -> claims in which the model cannot write a number.

The model writes sentences with slots: "The Sharpe ratio was {backtest.metrics.sharpe}".
A slot names a field of the Result; the value comes from the Result, never from the
model. A sentence that carries a digit of its own, or a slot that names nothing, is
dropped, not repaired and not shown. The renderer (web, through its number formatter)
receives segments, so formatting stays where the locale is.

The check this replaces, `web/src/routes/ai/numerals.ts`, scans an answer after the
fact. It stays for the one path that cannot use claims: Vibe-Trading's free text.
Words for numbers ("a third") and CJK numerals are not caught here.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .spec import Complete, extract_json

SLOT = re.compile(r"\{([^{}]*)\}")
# ASCII, Arabic-Indic, Extended Arabic-Indic and Devanagari digits, and full-width digits.
DIGIT = re.compile(r"[0-9٠-٩۰-۹०-९０-９]")
MISSING = object()


def resolve(result: dict, path: str):
    """`rows.0.symbol` -> the value, or MISSING. Dots only; a list takes an index."""
    node = result
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return MISSING
    return MISSING if isinstance(node, (dict, list)) else node


def segments(sentence: str, result: dict) -> list[dict] | str:
    """The sentence as [{"text"} | {"ref", "value"}], or the reason it is refused."""
    out: list[dict] = []
    pos = 0
    for m in SLOT.finditer(sentence):
        text = sentence[pos : m.start()]
        if DIGIT.search(text):
            return "carries a number of its own"
        if text:
            out.append({"text": text})
        path = m.group(1).strip()
        value = resolve(result, path)
        if value is MISSING:
            return f"slot {path!r} names nothing in the result"
        out.append({"ref": path, "value": value})
        pos = m.end()
    tail = sentence[pos:]
    if DIGIT.search(tail):
        return "carries a number of its own"
    if "{" in tail or "}" in tail:
        return "has an unclosed slot"
    if tail:
        out.append({"text": tail})
    if not any("text" in s and s["text"].strip() for s in out):
        return "says nothing"
    return out


@dataclass
class Claims:
    claims: list[list[dict]] = field(default_factory=list)
    dropped: list[tuple[str, str]] = field(default_factory=list)  # (sentence, reason)


def check_claims(sentences: list, result: dict) -> Claims:
    out = Claims()
    for sentence in sentences:
        if not isinstance(sentence, str):
            out.dropped.append((repr(sentence)[:80], "is not a sentence"))
            continue
        parsed = segments(sentence, result)
        if isinstance(parsed, str):
            out.dropped.append((sentence, parsed))
        else:
            out.claims.append(parsed)
    return out


def result_to_claims(result: dict, complete: Complete) -> Claims:
    """Ask the model to explain a Result; keep only what survives `check_claims`."""
    prompt = (
        "Explain this result in plain sentences, as {\"claims\": [\"...\"]}. Never write a digit. "
        "To mention a value, write its path in braces, such as {backtest.metrics.sharpe}. "
        "Name the rule, the result, and one limit. Do not advise buying or selling.\n\n"
        + json.dumps(result, ensure_ascii=False)
    )
    doc = extract_json(complete([{"role": "user", "content": prompt}]))
    sentences = doc.get("claims") if doc else None
    return check_claims(sentences if isinstance(sentences, list) else [], result)
