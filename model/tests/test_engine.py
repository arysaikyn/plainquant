import unittest

from ..backtest import marks_of, run_backtest
from ..factors import factor
from ..run import run, spec_hash
from ..screen import screen, select
from ..snapshot import Snapshot
from .fixtures import make_snapshot, spec

NOW = "2026-01-01T00:00:00Z"


class PointInTime(unittest.TestCase):
    snap = make_snapshot()

    def test_a_fact_is_invisible_before_its_announcement_date(self):
        self.assertIsNone(self.snap.fact_at("S000", "debt_ratio", "2019-04-29"))
        self.assertIsNotNone(self.snap.fact_at("S000", "debt_ratio", "2019-04-30"))

    def test_a_report_replaces_the_last_one_only_on_its_announcement_date(self):
        before = self.snap.fact_at("S000", "debt_ratio", "2020-04-29")
        after = self.snap.fact_at("S000", "debt_ratio", "2020-04-30")
        self.assertEqual(before, self.snap.facts["S000"][0][1]["debt_ratio"])
        self.assertEqual(after, self.snap.facts["S000"][1][1]["debt_ratio"])

    def test_a_suspended_name_carries_its_last_price(self):
        s = make_snapshot(n=1)
        del s.prices["S000"]["2020-03-04"]
        s.__post_init__()
        self.assertEqual(s.price_at("S000", "2020-03-04"), s.prices["S000"]["2020-03-03"])

    def test_a_future_restatement_cannot_move_a_past_ranking(self):
        # Change only a report announced after the date; the ranking on that date must not move.
        base = screen(spec(), self.snap, "2020-03-31")
        later = make_snapshot()
        for symbol in later.facts:
            later.facts[symbol][2][1]["debt_ratio"] = 0.99  # announced 2021-04-30
        later.__post_init__()
        self.assertEqual(base, screen(spec(), later, "2020-03-31"))


class Screen(unittest.TestCase):
    snap = make_snapshot()
    date = "2021-06-30"

    def test_ranks_best_first_and_respects_direction(self):
        ranked = screen(spec(rank=[{"factor": "debt_ratio", "direction": "asc"}], filters=[]), self.snap, self.date)
        debts = [r["factors"]["debt_ratio"] for r in ranked]
        self.assertEqual(debts, sorted(debts))

    def test_a_filter_removes_names_that_fail_it(self):
        ranked = screen(spec(), self.snap, self.date)
        self.assertTrue(ranked)
        self.assertTrue(all(r["factors"]["debt_ratio"] < 0.9 for r in ranked))

    def test_a_missing_input_is_out_not_zero(self):
        s = make_snapshot()
        s.facts["S000"][2][1]["dividend_yield"] = None
        s.__post_init__()
        self.assertNotIn("S000", [r["symbol"] for r in screen(spec(), s, self.date)])

    def test_sharia_runs_before_ranking_and_unknown_is_not_compliant(self):
        s = make_snapshot()
        s.facts["S001"][2][1]["receivables_ratio"] = None  # unproven
        s.facts["S002"][2][1]["debt_ratio"] = 0.5  # breach
        s.__post_init__()
        names = [r["symbol"] for r in screen(spec(sharia="compliant_only", filters=[]), s, self.date)]
        self.assertNotIn("S001", names)
        self.assertNotIn("S002", names)
        for r in screen(spec(sharia="compliant_only", filters=[]), s, self.date):
            self.assertEqual(r["sharia"], "compliant")

    def test_a_name_with_no_price_yet_is_never_picked(self):
        s = make_snapshot()
        s.prices["S000"] = {d: p for d, p in s.prices["S000"].items() if d >= "2022-01-01"}
        s.__post_init__()
        self.assertNotIn("S000", [r["symbol"] for r in screen(spec(), s, self.date)])


def ranked(*symbols):
    return [{"symbol": s} for s in symbols]


class Select(unittest.TestCase):
    def test_first_formation_takes_the_top_k(self):
        self.assertEqual(select([], ranked("a", "b", "c", "d"), top_k=2, n_drop=1), ["a", "b"])

    def test_with_no_drop_a_holding_stays_while_it_is_still_ranked(self):
        self.assertEqual(select(["d"], ranked("a", "b", "c", "d"), top_k=2, n_drop=0), ["d", "a"])

    def test_a_holding_that_leaves_the_screen_is_forced_out(self):
        self.assertEqual(select(["x", "a"], ranked("a", "b", "c"), top_k=2, n_drop=0), ["a", "b"])

    def test_n_drop_swaps_the_worst_held_for_the_best_waiting(self):
        self.assertEqual(select(["a", "d"], ranked("a", "b", "c", "d"), top_k=2, n_drop=1), ["a", "b"])

    def test_n_drop_never_sells_without_a_replacement(self):
        self.assertEqual(select(["a", "b"], ranked("a", "b"), top_k=2, n_drop=2), ["a", "b"])

    def test_never_holds_more_than_top_k(self):
        self.assertLessEqual(len(select(["a", "b", "c"], ranked("a", "b", "c", "d", "e"), 3, 2)), 3)


class Backtest(unittest.TestCase):
    def test_marks_start_the_window_then_close_each_period(self):
        marks = marks_of(make_snapshot(n=2), "M", "2020-01-01", "2020-03-31")
        self.assertEqual(marks, ["2020-01-01", "2020-01-31", "2020-02-28", "2020-03-31"])

    def test_flat_prices_leave_only_the_cost_of_building_the_book(self):
        s = make_snapshot(flat=True)
        out = run_backtest(spec(n_drop=0, filters=[]), s)  # no filter: nothing forces a sale
        rate = 0.0015 + 0.005
        self.assertAlmostEqual(out["curve"][1], 1 - rate, places=12)  # buy 100% of the book once
        self.assertAlmostEqual(out["metrics"]["max_drawdown"], -rate, places=12)

    def test_costs_only_ever_reduce_the_return(self):
        s = make_snapshot()
        free = run_backtest(spec(costs={"fee_rate": 0.0, "slip_rate": 0.0}), s)["metrics"]["annual_return"]
        paid = run_backtest(spec(), s)["metrics"]["annual_return"]
        self.assertLess(paid, free)

    def test_a_holding_that_never_leaves_costs_nothing_after_the_first_buy(self):
        s = make_snapshot(flat=True)
        out = run_backtest(spec(n_drop=0, filters=[]), s)
        self.assertEqual(out["metrics"]["turnover"], 0.0)

    def test_metrics_are_in_range(self):
        m = run_backtest(spec(), make_snapshot())["metrics"]
        self.assertLessEqual(m["max_drawdown"], 0)
        self.assertGreaterEqual(m["turnover"], 0)

    def test_a_period_with_one_date_is_refused(self):
        with self.assertRaises(ValueError):
            run_backtest(spec(period={"start": "2020-01-01", "end": "2020-01-01"}), make_snapshot(n=2))


class Run(unittest.TestCase):
    snap = make_snapshot()

    def test_same_spec_same_data_same_result(self):
        self.assertEqual(run(spec(), self.snap, "q", NOW), run(spec(), self.snap, "q", NOW))

    def test_the_receipt_pins_the_spec_the_data_and_the_engine(self):
        r = run(spec(), self.snap, "q", NOW)
        self.assertEqual(r["receipt"]["spec_hash"], spec_hash(spec()))
        self.assertEqual(r["receipt"]["data_version"], "synthetic-seed1")
        self.assertNotEqual(spec_hash(spec()), spec_hash(spec(top_k=11)))

    def test_under_compliant_only_every_row_is_compliant(self):
        r = run(spec(sharia="compliant_only"), self.snap, "q", NOW)
        self.assertTrue(r["rows"])
        self.assertTrue(all(row["sharia"] == "compliant" for row in r["rows"]))
        self.assertIn("sharia", r["audit"]["grid"]["families"])

    def test_rows_are_the_holdings_ranked_with_equal_weight(self):
        r = run(spec(), self.snap, "q", NOW)
        self.assertEqual([row["rank"] for row in r["rows"]], list(range(1, len(r["rows"]) + 1)))
        self.assertAlmostEqual(sum(row["weight"] for row in r["rows"]), 1.0)

    def test_a_field_the_contract_does_not_define_is_refused_even_unvalidated(self):
        for bad in (spec(stop_loss=0.05), spec(take_profit=0.1), spec(entry_price=10)):
            with self.assertRaisesRegex(ValueError, "does not define"):
                run(bad, self.snap, "q", NOW)
        nested = spec(filters=[{"factor": "debt_ratio", "op": "lt", "value": 0.9, "stop": 1}])
        with self.assertRaisesRegex(ValueError, r"filters\[0\]\.stop"):
            run(nested, self.snap, "q", NOW)

    def test_an_unregistered_factor_is_refused(self):
        with self.assertRaises(ValueError):
            run(spec(rank=[{"factor": "vibes", "direction": "desc"}]), self.snap, "q", NOW)

    def test_a_snapshot_for_another_universe_is_refused(self):
        with self.assertRaises(ValueError):
            run(spec(universe="csi300"), self.snap, "q", NOW)

    def test_a_price_only_spec_is_charged_by_the_audit(self):
        r = run(spec(filters=[], rank=[{"factor": "momentum_6m", "direction": "desc"}]), self.snap, "q", NOW)
        self.assertIn("priceOnly", [f["id"] for f in r["audit"]["grid"]["findings"]])

    def test_a_fundamental_spec_is_not(self):
        r = run(spec(), self.snap, "q", NOW)
        self.assertNotIn("priceOnly", [f["id"] for f in r["audit"]["grid"]["findings"]])

    def test_every_registered_factor_has_a_known_family(self):
        from ..audit import PRICE_BLOCK
        from ..factors import REGISTRY

        for f in REGISTRY.values():
            self.assertIn(factor(f.id).family, PRICE_BLOCK)


if __name__ == "__main__":
    unittest.main()
