import unittest

from .. import markets
from ..backtest import fill_date, marks_of, run_backtest, tradable_book
from ..factors import factor
from ..run import run, spec_hash
from ..screen import screen, select
from ..snapshot import Snapshot
import dataclasses
from unittest import mock
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

    def test_prices_after_the_ranking_day_cannot_move_the_ranking(self):
        day = "2021-06-30"
        momentum = spec(filters=[], rank=[{"factor": "momentum_6m", "direction": "desc"}])
        before = screen(momentum, self.snap, day)
        future = make_snapshot()
        for series in future.prices.values():
            for d in series:
                if d > day:
                    series[d] *= 10
        future.__post_init__()
        self.assertEqual(before, screen(momentum, future, day))

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

    def test_a_rebalance_is_filled_on_the_next_trading_day_not_on_the_ranking_close(self):
        snap = make_snapshot()
        s = spec(top_k=1, n_drop=0, filters=[], rank=[{"factor": "debt_ratio", "direction": "asc"}])
        out = run_backtest(s, snap)
        marks = marks_of(snap, "M", s["period"]["start"], s["period"]["end"])
        self.assertEqual(out["dates"][0], fill_date(snap, marks[0]))
        self.assertGreater(out["dates"][0], marks[0])
        held = screen(s, snap, marks[0])[0]["symbol"]
        move = snap.price_at(held, out["dates"][1]) / snap.price_at(held, out["dates"][0]) - 1
        cost = 0.0015 + 0.005  # the whole book is bought once, so the traded weight is 1
        self.assertAlmostEqual(out["curve"][1] - 1, move - cost, places=12)

    def test_the_last_period_of_the_data_uses_the_last_day_as_its_fill(self):
        snap = make_snapshot()
        self.assertEqual(fill_date(snap, snap.dates[-1]), snap.dates[-1])
        self.assertEqual(fill_date(snap, snap.dates[0]), snap.dates[1])

    def test_nothing_after_the_last_fill_is_ever_read(self):
        snap = make_snapshot()
        s = spec(period={"start": "2020-01-01", "end": "2024-06-30"})
        full = run_backtest(s, snap)
        last = full["dates"][-1]
        cut = dataclasses.replace(
            snap,
            dates=[d for d in snap.dates if d <= last],
            prices={sym: {d: p for d, p in series.items() if d <= last} for sym, series in snap.prices.items()},
            facts={sym: [(d, row) for d, row in rows if d <= last] for sym, rows in snap.facts.items()},
        )
        self.assertLess(len(cut.dates), len(snap.dates))
        again = run_backtest(s, cut)
        self.assertEqual((again["curve"], again["bench"], again["metrics"]), (full["curve"], full["bench"], full["metrics"]))

    def test_a_period_with_one_date_is_refused(self):
        with self.assertRaises(ValueError):
            run_backtest(spec(period={"start": "2020-01-01", "end": "2020-01-01"}), make_snapshot(n=2))


class Tradability(unittest.TestCase):
    """A name with no price on the fill day cannot be traded that day."""

    def setUp(self):
        self.snap = make_snapshot(n=6)
        self.day = "2021-03-03"

    def suspend(self, *names):
        for n in names:
            del self.snap.prices[n][self.day]
        self.snap.__post_init__()

    def test_a_suspended_name_is_not_bought_and_its_slot_stays_empty(self):
        self.suspend("S002")
        self.assertEqual(tradable_book(self.snap, "cn_a", [], ["S001", "S002", "S003"], self.day), ["S001", "S003"])

    def test_a_suspended_name_that_should_be_sold_is_kept(self):
        self.suspend("S001")
        self.assertEqual(tradable_book(self.snap, "cn_a", ["S001", "S002"], ["S002", "S003"], self.day), ["S002", "S003", "S001"])

    def test_a_suspended_name_already_held_and_still_wanted_stays_once(self):
        self.suspend("S001")
        self.assertEqual(tradable_book(self.snap, "cn_a", ["S001"], ["S001", "S002"], self.day), ["S001", "S002"])

    def test_when_nothing_is_suspended_the_book_is_the_target(self):
        self.assertEqual(tradable_book(self.snap, "cn_a", ["S001"], ["S002", "S003"], self.day), ["S002", "S003"])

    def test_the_best_name_suspended_on_the_first_fill_day_is_not_in_the_first_book(self):
        snap = make_snapshot()
        s = spec(top_k=3, n_drop=0, filters=[], rank=[{"factor": "debt_ratio", "direction": "asc"}])
        marks = marks_of(snap, "M", s["period"]["start"], s["period"]["end"])
        best = screen(s, snap, marks[0])[0]["symbol"]
        del snap.prices[best][fill_date(snap, marks[0])]
        snap.__post_init__()
        books = run_backtest(s, snap)["books"]
        self.assertNotIn(best, books[0])
        self.assertEqual(len(books[0]), 2)


class PriceLimits(unittest.TestCase):
    """A name that closes at its daily limit cannot be bought up, or sold down."""

    def setUp(self):
        self.snap = make_snapshot(n=6)
        self.day = "2021-03-03"
        i = self.snap.dates.index(self.day)
        self.before = self.snap.dates[i - 1]
        # The synthetic symbols start with "S", so give the market a 10% limit for them.
        limited = dataclasses.replace(markets.MARKETS["cn_a"], limits=((("S",), "0000-01-01", 0.10),))
        patch = mock.patch.dict(markets.MARKETS, {"cn_a": limited})
        patch.start()
        self.addCleanup(patch.stop)

    def move(self, name, ret):
        self.snap.prices[name][self.day] = self.snap.prices[name][self.before] * (1 + ret)
        self.snap.__post_init__()

    def book(self, held, target):
        return tradable_book(self.snap, "cn_a", held, target, self.day)

    def test_a_name_at_its_up_limit_is_not_bought(self):
        self.move("S002", 0.10)
        self.assertEqual(self.book([], ["S001", "S002", "S003"]), ["S001", "S003"])

    def test_the_up_limit_does_not_stop_a_sale(self):
        self.move("S001", 0.10)
        self.assertEqual(self.book(["S001"], ["S002"]), ["S002"])

    def test_a_name_at_its_down_limit_cannot_be_sold(self):
        self.move("S001", -0.10)
        self.assertEqual(self.book(["S001", "S002"], ["S002", "S003"]), ["S002", "S003", "S001"])

    def test_the_down_limit_does_not_stop_a_purchase(self):
        self.move("S002", -0.10)
        self.assertEqual(self.book([], ["S002"]), ["S002"])

    def test_a_rise_clearly_below_the_limit_is_bought(self):
        self.move("S002", 0.08)
        self.assertEqual(self.book([], ["S002"]), ["S002"])

    def test_a_price_tick_below_the_limit_still_counts_as_the_limit(self):
        self.move("S002", 0.097)
        self.assertEqual(self.book([], ["S002"]), [])


class BoardLimits(unittest.TestCase):
    def test_limits_by_board_and_date(self):
        self.assertEqual(markets.price_limit("cn_a", "600519.SH", "2024-01-02"), 0.10)
        self.assertEqual(markets.price_limit("cn_a", "688981.SH", "2024-01-02"), 0.20)
        self.assertEqual(markets.price_limit("cn_a", "300750.SZ", "2020-08-21"), 0.10)
        self.assertEqual(markets.price_limit("cn_a", "300750.SZ", "2020-08-24"), 0.20)
        self.assertIsNone(markets.price_limit("cn_a", "S001", "2024-01-02"))


class SellTax(unittest.TestCase):
    def test_the_rate_changes_on_the_day_the_duty_was_halved(self):
        self.assertEqual(markets.sell_tax_rate("cn_a", "2023-08-27"), 0.001)
        self.assertEqual(markets.sell_tax_rate("cn_a", "2023-08-28"), 0.0005)
        self.assertEqual(markets.sell_tax_rate("cn_a", "2019-01-02"), 0.001)

    def test_an_unregistered_market_has_no_rate(self):
        with self.assertRaisesRegex(ValueError, "no market rules are registered"):
            markets.sell_tax_rate("sa", "2024-01-02")

    def test_only_the_sale_pays_it(self):
        # Flat prices, so a period's return is exactly minus its costs. The book swaps 2 of 10
        # names each period, so 20% of the book is sold, and a buy-only period pays no duty.
        snap = make_snapshot(flat=True)
        s = spec(n_drop=2, filters=[], period={"start": "2020-01-01", "end": "2020-12-31"})
        taxed = run_backtest(s, snap)["curve"]
        free_rules = markets.MarketRules(frictions=markets.MARKETS["cn_a"].frictions, sell_tax=(("0000-01-01", 0.0),))
        with mock.patch.dict(markets.MARKETS, {"cn_a": free_rules}):
            free = run_backtest(s, snap)["curve"]
        self.assertEqual(taxed[1], free[1])  # the first period only buys
        step = lambda c, i: c[i + 1] / c[i] - 1
        self.assertAlmostEqual(step(taxed, 1) - step(free, 1), -0.2 * 0.001, places=12)

    def test_the_halved_rate_applies_to_a_sale_after_the_change(self):
        snap = make_snapshot(flat=True)
        s = spec(n_drop=2, filters=[], period={"start": "2023-10-02", "end": "2023-12-29"})
        taxed = run_backtest(s, snap)["curve"]
        free_rules = markets.MarketRules(frictions=markets.MARKETS["cn_a"].frictions, sell_tax=(("0000-01-01", 0.0),))
        with mock.patch.dict(markets.MARKETS, {"cn_a": free_rules}):
            free = run_backtest(s, snap)["curve"]
        step = lambda c, i: c[i + 1] / c[i] - 1
        self.assertAlmostEqual(step(taxed, 1) - step(free, 1), -0.2 * 0.0005, places=12)

    def test_the_market_note_says_stamp_duty_and_suspension_are_modelled(self):
        text = markets.warning("cn_a")
        self.assertTrue(text.startswith("Not modelled for cn_a: T+1 settlement, the 5% limit of ST names, 100-share board lots."))
        self.assertIn("suspended", text)
        self.assertIn("Stamp duty on sales", text)


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

    def test_a_market_with_no_registered_rules_is_refused(self):
        snap = make_snapshot(market="sa")
        with self.assertRaisesRegex(ValueError, "no market rules are registered for 'sa'"):
            run(spec(market="sa"), snap, "q", NOW)

    def test_a_snapshot_from_another_market_is_refused(self):
        with self.assertRaisesRegex(ValueError, "snapshot carries market 'cn_a'"):
            run(spec(market="us"), self.snap, "q", NOW)

    def test_every_result_says_what_the_market_model_leaves_out(self):
        warnings = run(spec(), self.snap, "q", NOW)["warnings"]
        self.assertIn("Not modelled for cn_a: T+1 settlement, the 5% limit of ST names, 100-share board lots.", warnings[0])

    def test_the_known_limits_of_the_data_are_repeated_in_every_result(self):
        snap = make_snapshot()
        snap.limitations = ["Universe is today's list, so names that left it are missing."]
        warnings = run(spec(), snap, "q", NOW)["warnings"]
        self.assertIn("Data: Universe is today's list, so names that left it are missing.", warnings)
        self.assertTrue(warnings[0].startswith("Not modelled"))

    def test_a_short_book_adds_its_own_note_after_the_market_note(self):
        warnings = run(spec(sharia="compliant_only", top_k=40), self.snap, "q", NOW)["warnings"]
        self.assertTrue(warnings[0].startswith("Not modelled"))
        self.assertTrue(any(w.startswith("only ") for w in warnings[1:]))

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
