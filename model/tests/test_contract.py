"""The two schemas hold, and the engine's output satisfies them.

Needs `jsonschema`; without it the tests are skipped, never passed.
"""

import copy
import json
import unittest
from pathlib import Path

from ..run import run, spec_hash
from .fixtures import make_snapshot, spec

try:
    from jsonschema import Draft202012Validator, RefResolver
except ImportError:  # pragma: no cover
    Draft202012Validator = None

MODEL = Path(__file__).resolve().parent.parent
SPEC_S = json.loads((MODEL / "spec.schema.json").read_text())
SIG_S = json.loads((MODEL / "signals.schema.json").read_text())
EXAMPLE = json.loads((MODEL / "signals.example.json").read_text())


def validator(schema):
    store = {SPEC_S["$id"]: SPEC_S, SIG_S["$id"]: SIG_S}
    return Draft202012Validator(schema, resolver=RefResolver.from_schema(schema, store=store))


@unittest.skipIf(Draft202012Validator is None, "jsonschema is not installed")
class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Draft202012Validator.check_schema(SPEC_S)
        Draft202012Validator.check_schema(SIG_S)
        cls.sig, cls.spec = validator(SIG_S), validator(SPEC_S)

    def rejects(self, doc, schema=None):
        self.assertTrue(list((schema or self.sig).iter_errors(doc)))

    def mut(self, fn, base=None):
        d = copy.deepcopy(base or EXAMPLE)
        fn(d)
        return d

    def test_the_example_validates_and_its_hash_matches_its_spec(self):
        self.assertEqual(list(self.sig.iter_errors(EXAMPLE)), [])
        self.assertEqual(EXAMPLE["receipt"]["spec_hash"], spec_hash(EXAMPLE["spec"]))

    def test_the_engine_output_validates(self):
        snap = make_snapshot()
        for s in (spec(), spec(sharia="compliant_only"), spec(rebalance="Q", top_k=5)):
            result = run(s, snap, "q", "2026-01-01T00:00:00Z")
            self.assertEqual(list(self.sig.iter_errors(result)), [], s)

    def test_no_price_level_field_can_enter_a_spec(self):
        for key in ("stop_loss", "take_profit", "entry_price"):
            self.rejects(self.mut(lambda d, k=key: d["spec"].update({k: 1})))
            self.rejects(self.mut(lambda d, k=key: d.update({k: 1})))

    def test_a_spec_must_state_how_a_holding_ends(self):
        self.rejects(self.mut(lambda d: d["spec"].pop("n_drop")))

    def test_a_result_cannot_omit_its_audit_receipt_or_spec(self):
        for key in ("audit", "receipt", "spec"):
            self.rejects(self.mut(lambda d, k=key: d.pop(k)))

    def test_only_the_current_version_is_accepted(self):
        self.rejects(self.mut(lambda d: d.update(schema_version="1.1")))

    def test_the_hash_must_be_a_sha256(self):
        self.rejects(self.mut(lambda d: d["receipt"].update(spec_hash="abc")))

    def test_under_compliant_only_only_compliant_rows_are_ranked(self):
        def on(d):
            d["spec"]["sharia"] = "compliant_only"

        def ok(d):
            on(d)
            for r in d["rows"]:
                r["sharia"] = "compliant"

        self.rejects(self.mut(on))  # rows are unknown
        self.assertEqual(list(self.sig.iter_errors(self.mut(ok))), [])

        def breach(d):
            ok(d)
            d["rows"][0]["sharia"] = "non_compliant"

        def silent(d):
            ok(d)
            d["rows"][0].pop("sharia")

        self.rejects(self.mut(breach))
        self.rejects(self.mut(silent))


if __name__ == "__main__":
    unittest.main()
