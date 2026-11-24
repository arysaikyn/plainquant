"""Facts that Python and TypeScript both state must stay equal until web/ stops stating them.

web/src still holds its own copy of the AAOIFI caps, the demo fee and slippage, and the
refusal rule names, because the screens that use them still compute in the browser.
Each test reads the TypeScript source and compares it with the Python owner, so a change
on one side fails the engine job instead of waiting for someone to remember.
"""

import re
import unittest
from pathlib import Path

from agent.spec import DEFAULTS, REFUSALS
from model import sharia

WEB = Path(__file__).resolve().parents[2] / "web" / "src"


def number_fields(text: str, block_start: str) -> dict[str, float]:
    """`name: 0.3,` pairs of the object literal that follows `block_start`."""
    start = text.index(block_start)
    body = text[text.index("{", start) : text.index("}", start)]
    return {k: float(v) for k, v in re.findall(r"(\w+):\s*(-?\d+(?:\.\d+)?)", body)}


def snake(name: str) -> str:
    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), name)


class SharedFacts(unittest.TestCase):
    def test_the_aaoifi_caps_equal_the_ones_the_browser_still_uses(self):
        ts = number_fields((WEB / "data" / "shariaCoverage.ts").read_text(), "export const SHARIA_LIMITS")
        self.assertEqual({snake(k): v for k, v in ts.items()}, {k: cap for k, (_, cap) in sharia.FIELDS.items()})

    def test_the_default_costs_equal_the_demo_costs(self):
        ts = number_fields((WEB / "data" / "costs.ts").read_text(), "export const DEMO_COSTS")
        self.assertEqual(ts["feeRate"], DEFAULTS["fee_rate"])
        self.assertEqual(ts["slipRate"], DEFAULTS["slip_rate"])

    def test_the_refusal_rules_equal_the_ones_the_chat_screen_names(self):
        text = (WEB / "lib" / "refusal.ts").read_text()
        line = re.search(r"export type RefusalRule = ([^\n]+)", text).group(1)
        self.assertEqual(set(re.findall(r"'(\w+)'", line)), set(REFUSALS))


if __name__ == "__main__":
    unittest.main()
