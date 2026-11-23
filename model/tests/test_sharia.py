"""The verdict is a filter before ranking, so its precedence is a product rule."""

import unittest

from .. import sharia

CLEAN = {"debt_ratio": 0.1, "interest_bearing_ratio": 0.1, "impure_income_ratio": 0.01, "receivables_ratio": 0.1}


def verdict(**changes):
    values = {**CLEAN, **changes}
    return sharia.verdict(values.get)


class Verdict(unittest.TestCase):
    def test_every_ratio_under_the_cap_is_compliant_with_no_reasons(self):
        v = verdict()
        self.assertEqual((v["status"], v["failed"], v["missing"]), ("compliant", [], []))

    def test_a_breach_names_its_field_and_limit(self):
        v = verdict(debt_ratio=0.5)
        self.assertEqual(v["status"], "non_compliant")
        self.assertEqual((v["failed"][0]["field"], v["failed"][0]["limit"]), ("debt", 0.3))

    def test_a_missing_ratio_leaves_the_name_unproven_even_without_a_breach(self):
        v = verdict(receivables_ratio=None)
        self.assertEqual((v["status"], v["missing"]), ("unknown", ["receivables"]))

    def test_a_missing_input_outranks_a_breach(self):
        v = verdict(receivables_ratio=None, debt_ratio=0.9)
        self.assertEqual(v["status"], "unknown")
        self.assertEqual(v["failed"][0]["field"], "debt")

    def test_the_cap_itself_passes(self):
        self.assertEqual(verdict(debt_ratio=0.3)["status"], "compliant")

    def test_nan_is_missing_not_zero(self):
        self.assertEqual(verdict(debt_ratio=float("nan"))["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
