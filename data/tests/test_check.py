import tempfile
import unittest

from data import check as chk
from model import store
from model.tests.fixtures import make_snapshot


def levels(snap):
    return {f.what: f.level for f in chk.check(snap)}


class Check(unittest.TestCase):
    def test_a_clean_snapshot_has_no_error_and_no_warning(self):
        got = levels(make_snapshot(n=20))
        self.assertEqual({k: v for k, v in got.items() if v != "info"}, {})

    def test_a_real_holiday_is_not_a_hole_but_a_missing_month_is(self):
        snap = make_snapshot(n=5)
        # Spring Festival 2020 closed 11 calendar days between two trading days.
        snap.dates = [d for d in snap.dates if not ("2020-01-24" <= d <= "2020-02-02")]
        self.assertNotEqual(levels(snap)["calendar"], "error")

    def test_a_hole_in_the_calendar_is_an_error(self):
        snap = make_snapshot(n=5)
        keep = [d for d in snap.dates if not ("2021-03-01" <= d <= "2021-03-31")]
        snap.dates = keep
        self.assertEqual(levels(snap)["calendar"], "error")

    def test_a_huge_one_day_move_is_a_warning_naming_the_name(self):
        snap = make_snapshot(n=5)
        day = snap.dates[400]
        snap.prices["S002"][day] *= 3
        found = {f.what: f for f in chk.check(snap)}["price jumps"]
        self.assertEqual(found.level, "warn")
        self.assertIn("S002", found.detail)

    def test_a_debt_ratio_outside_zero_to_one_is_an_error(self):
        snap = make_snapshot(n=5)
        snap.facts["S001"][2][1]["debt_ratio"] = 1.7
        self.assertEqual(levels(snap)["debt_ratio"], "error")
        snap.facts["S001"][2][1]["debt_ratio"] = 0.009  # a value in range is not judged here
        self.assertEqual(levels(snap)["debt_ratio"], "info")

    def test_a_name_with_no_report_is_an_error(self):
        snap = make_snapshot(n=5)
        snap.facts["S003"] = []
        self.assertEqual(levels(snap)["reports"], "error")

    def test_a_series_that_ends_early_is_a_warning(self):
        snap = make_snapshot(n=5)
        cut = snap.dates[-200]
        snap.prices["S004"] = {d: p for d, p in snap.prices["S004"].items() if d <= cut}
        snap.__post_init__()
        self.assertEqual(levels(snap)["ended series"], "warn")

    def test_months_with_few_tradable_members_are_a_warning(self):
        snap = make_snapshot(n=20)
        for sym in list(snap.membership)[:12]:
            snap.membership[sym] = [(snap.dates[0], "2020-06-30"), ("2020-09-01", None)]  # most of the index is gone for two months
        self.assertEqual(levels(snap)["members"], "warn")

    def test_the_command_exit_code_follows_the_worst_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            store.write(make_snapshot(n=8), f"{tmp}/ok")
            bad = make_snapshot(n=8)
            bad.facts["S000"][0][1]["debt_ratio"] = 2.0
            store.write(bad, f"{tmp}/bad")
            self.assertEqual(chk.main([f"{tmp}/ok"]), 0)
            self.assertEqual(chk.main([f"{tmp}/bad"]), 1)
            self.assertEqual(chk.main([f"{tmp}/missing"]), 2)


if __name__ == "__main__":
    unittest.main()
