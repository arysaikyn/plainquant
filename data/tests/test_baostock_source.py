"""The Baostock builder, run against a fake service. No network, no vendor data.

The fake answers in the shape the real library does (error_code, fields, next(),
get_row_data()). Whether the real server uses the same field names is NOT checked here;
that is what the first live run is for, and `need()` is what makes it say so.
"""

import random
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from data import baostock_source as src
from model import store
from model.run import run
from model.tests.test_contract import Draft202012Validator, SIG_S, validator

NOW = "2026-01-01T00:00:00Z"


class Rs:
    def __init__(self, fields, rows, code="0", msg="success"):
        self.fields, self._rows, self.error_code, self.error_msg, self._i = fields, rows, code, msg, -1

    def next(self):
        self._i += 1
        return self._i < len(self._rows)

    def get_row_data(self):
        return self._rows[self._i]


def weekdays(start, end):
    d, out = start, []
    while d <= end:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


class FakeBs:
    """Six names, two years of weekdays, quarterly reports, one dividend a year."""

    def __init__(self, names=6, suspended=(), lists=None, scale_bug_from=None, no_multiplier=()):
        rng = random.Random(7)
        self.codes = [f"sh.60{i:04d}" for i in range(names)]
        self.days = weekdays(date(2018, 1, 1), date(2019, 12, 31))
        self.debt = {c: rng.uniform(0.2, 0.9) for c in self.codes}
        self.series = {}
        for c in self.codes:
            level, out = 10.0, {}
            for d in self.days:
                level *= 1 + rng.gauss(0.0004, 0.012)
                out[d] = level
            self.series[c] = out
        self.suspended = set(suspended)
        self.lists = lists  # {sample day: codes}; None means the same list on every day
        self.scale_bug_from = scale_bug_from  # reports published from this day carry the real 100x defect
        self.no_multiplier = set(no_multiplier)  # (code, year, quarter) with an empty assetToEquity

    def login(self):
        return Rs([], [])

    def logout(self):
        return Rs([], [])

    def query_hs300_stocks(self, date=""):
        codes = self.codes
        if self.lists is not None:
            days = [d for d in sorted(self.lists) if d <= date]
            codes = sorted(self.lists[days[-1]]) if days else []
        return Rs(["updateDate", "code", "code_name"], [["2024-12-30", c, f"Name {c[-2:]}"] for c in codes])

    def query_history_k_data_plus(self, code, fields, start_date, end_date, frequency, adjustflag):
        rows = []
        for d, price in self.series[code].items():
            if start_date <= d <= end_date and code not in self.suspended:
                raw = price if adjustflag == "3" else price * 1.5  # back-adjusted differs from raw
                rows.append([d, f"{raw:.4f}", "1"])
        return Rs(["date", "close", "tradestatus"], rows)

    def query_balance_data(self, code, year, quarter):
        published = {1: f"{year}-04-25", 2: f"{year}-08-25", 3: f"{year}-10-25", 4: f"{year + 1}-04-25"}[quarter]
        ratio = self.debt[code] + 0.01 * quarter
        stated = ratio * 0.01 if self.scale_bug_from and published >= self.scale_bug_from else ratio
        multiplier = "" if (code, year, quarter) in self.no_multiplier else f"{1 / (1 - ratio):.6f}"
        return Rs(
            ["code", "pubDate", "statDate", "liabilityToAsset", "assetToEquity"],
            [[code, published, f"{year}-{quarter * 3:02d}-30", f"{stated:.6f}", multiplier]],
        )

    def query_dividend_data(self, code, year, yearType):
        return Rs(["code", "dividPlanAnnounceDate", "dividCashPsBeforeTax"], [[code, f"{int(year) + 1}-03-20", "0.3"]])

    def query_stock_industry(self, code):
        return Rs(["code", "industry"], [[code, "J66货币金融服务" if code.endswith("1") else ""]])


class Pieces(unittest.TestCase):
    def test_symbols_use_the_contract_form(self):
        self.assertEqual(src.symbol("sh.600036"), "600036.SH")
        self.assertEqual(src.symbol("sz.000001"), "000001.SZ")

    def test_a_suspended_or_non_positive_day_is_absent_not_zero(self):
        class Bs(FakeBs):
            def query_history_k_data_plus(self, *a, **k):
                return Rs(["date", "close", "tradestatus"], [["2019-01-02", "10", "1"], ["2019-01-03", "10", "0"], ["2019-01-04", "0", "1"], ["2019-01-07", "", "1"]])

        self.assertEqual(src.closes(Bs(1), "sh.600000", "2019-01-01", "2019-01-31", "1"), {"2019-01-02": 10.0})

    def test_a_server_error_surfaces_with_the_servers_own_message(self):
        with self.assertRaisesRegex(src.SourceError, "10001001 not logged in"):
            src.query(Rs([], [], code="10001001", msg="not logged in"), "test")

    def test_a_missing_field_names_the_fields_the_server_sent(self):
        with self.assertRaisesRegex(src.SourceError, r"no field 'liabilityToAsset'.*\['code', 'pubDate'\]"):
            src.need({"code": "x", "pubDate": "y"}, "liabilityToAsset", "balance")

    def test_the_fact_rows_carry_every_known_value_forward(self):
        raw = {"2019-01-02": 10.0, "2019-06-03": 20.0}
        rows = dict(src.fact_rows([("2019-04-20", 0.9)], [("2019-06-01", 0.5)], raw))
        self.assertEqual(rows["2019-04-20"], {"debt_ratio": 0.9, "dividend_yield": 0.0})
        self.assertEqual(rows["2019-06-01"], {"debt_ratio": 0.9, "dividend_yield": 0.5 / 10.0})

    def test_nothing_is_known_before_the_first_price(self):
        rows = dict(src.fact_rows([("2019-04-20", 0.9)], [], {"2019-05-01": 10.0}))
        self.assertEqual(rows["2019-04-20"], {"debt_ratio": 0.9})  # no yield: no price yet

    def test_a_dividend_older_than_a_year_drops_out_of_the_yield(self):
        raw = {"2018-01-02": 10.0}
        rows = dict(src.fact_rows([], [("2018-03-01", 1.0), ("2019-06-01", 0.5)], {**raw, "2019-05-30": 10.0}))
        self.assertEqual(rows["2019-06-01"]["dividend_yield"], 0.05)

    def test_a_report_is_invisible_before_its_publication_date_on_the_built_snapshot(self):
        snap = src.build(FakeBs(2), "2019-01-01", "2019-12-31")
        sym = "600000.SH"
        self.assertIsNone(snap.fact_at(sym, "debt_ratio", "2018-04-24"))  # first fake report is published 2018-04-25
        self.assertIsNotNone(snap.fact_at(sym, "debt_ratio", "2018-04-25"))


class PointInTimeMembership(unittest.TestCase):
    def test_the_sample_days_are_the_start_and_each_half_year_after_it(self):
        self.assertEqual(src.sample_days("2019-01-01", "2020-03-01"), ["2019-01-01", "2019-07-01", "2020-01-01"])
        self.assertEqual(src.sample_days("2019-03-15", "2019-12-31"), ["2019-03-15", "2019-07-01"])
        self.assertEqual(src.sample_days("2019-07-01", "2019-12-31"), ["2019-07-01"])

    def test_a_code_is_a_member_from_the_sample_that_lists_it_to_the_day_before_the_one_that_does_not(self):
        lists = [("2019-01-01", {"A", "B"}), ("2019-07-01", {"A", "C"}), ("2020-01-01", {"A", "B", "C"})]
        self.assertEqual(
            src.membership_intervals(lists),
            {
                "A": [("2019-01-01", None)],
                "B": [("2019-01-01", "2019-06-30"), ("2020-01-01", None)],  # left, then came back
                "C": [("2019-07-01", None)],
            },
        )

    def test_the_built_universe_changes_with_the_published_list(self):
        codes = ["sh.600000", "sh.600001", "sh.600002", "sh.600003"]
        bs = FakeBs(4, lists={"2019-01-01": set(codes[:3]), "2019-07-01": {codes[0], codes[1], codes[3]}})
        snap = src.build(bs, "2019-01-01", "2019-12-31")
        self.assertEqual(snap.universe_at("2019-03-04"), ["600000.SH", "600001.SH", "600002.SH"])
        self.assertEqual(snap.universe_at("2019-09-03"), ["600000.SH", "600001.SH", "600003.SH"])
        self.assertEqual(snap.universe_at("2019-06-28"), ["600000.SH", "600001.SH", "600002.SH"])  # the list holds until the next sample


class DebtRatioCrossCheck(unittest.TestCase):
    """The live server scales liabilityToAsset 100 times too small in newer reports."""

    def test_the_ratio_comes_from_the_equity_multiplier_not_from_the_scaled_field(self):
        bs = FakeBs(2, scale_bug_from="2019-01-01")
        snap = src.build(bs, "2019-01-01", "2019-12-31")
        expected = bs.debt["sh.600000"] + 0.01 * 1  # the first quarter of 2019, published 2019-04-25
        self.assertAlmostEqual(snap.fact_at("600000.SH", "debt_ratio", "2019-05-02"), expected, places=5)
        self.assertGreater(snap.fact_at("600000.SH", "debt_ratio", "2019-05-02"), 0.1)

    def test_the_snapshot_counts_how_often_the_source_disagreed_with_itself(self):
        text = " ".join(src.build(FakeBs(2, scale_bug_from="2019-01-01"), "2019-01-01", "2019-12-31").limitations)
        self.assertRegex(text, r"liabilityToAsset disagreed with it in [1-9]\d* of \d+ reports")
        clean = " ".join(src.build(FakeBs(2), "2019-01-01", "2019-12-31").limitations)
        self.assertRegex(clean, r"disagreed with it in 0 of \d+ reports")

    def test_a_report_with_no_usable_equity_multiplier_is_dropped_and_counted(self):
        quality = src.Quality()
        bs = FakeBs(1, no_multiplier={("sh.600000", 2019, 2)})
        reports = src.debt_reports(bs, "sh.600000", range(2019, 2020), quality)
        self.assertEqual((len(reports), quality.reports, quality.skipped), (3, 3, 1))


class DroppedConnection(unittest.TestCase):
    def flaky(self, fails):
        class Bs(FakeBs):
            calls = {}
            logins = 0

            def login(self):
                Bs.logins += 1
                return Rs([], [])

            def query_balance_data(self, code, year, quarter):
                n = Bs.calls[code] = Bs.calls.get(code, 0) + 1
                if code in fails and n <= fails[code]:
                    return Rs([], [], code="10002007", msg="network receive error")
                return super().query_balance_data(code, year, quarter)

        return Bs(3)

    def test_a_name_that_fails_once_is_retried_after_logging_in_again(self):
        bs = self.flaky({"sh.600001": 1})
        snap = src.build(bs, "2019-01-01", "2019-12-31")
        self.assertIn("600001.SH", snap.prices)
        self.assertGreaterEqual(type(bs).logins, 1)
        self.assertFalse(any("could not be fetched" in text for text in snap.limitations))

    def test_a_retry_does_not_count_a_report_twice(self):
        clean = src.build(FakeBs(3), "2019-01-01", "2019-12-31")
        retried = src.build(self.flaky({"sh.600001": 1}), "2019-01-01", "2019-12-31")
        count = lambda s: [t for t in s.limitations if t.startswith("debt_ratio is 1 - 1/assetToEquity")]
        self.assertEqual(count(clean), count(retried))

    def test_a_name_that_never_answers_is_skipped_and_named_in_the_limitations(self):
        bs = self.flaky({"sh.600002": 99})
        snap = src.build(bs, "2019-01-01", "2019-12-31")
        self.assertEqual(sorted(snap.prices), ["600000.SH", "600001.SH"])
        self.assertTrue(any("1 names could not be fetched after 3 tries and are missing: sh.600002" in t for t in snap.limitations))


class SamePublicationDay(unittest.TestCase):
    def test_the_report_for_the_later_period_wins_when_two_are_published_on_one_day(self):
        # The fake publishes the 2018 annual report and the 2019 first quarter on 2019-04-25.
        bs = FakeBs(1)
        reports = src.debt_reports(bs, "sh.600000", range(2018, 2020), src.Quality())
        same_day = [r for d, r in reports if d == "2019-04-25"]
        self.assertEqual(len(same_day), 2)
        snap = src.build(bs, "2019-01-01", "2019-12-31")
        first_quarter = bs.debt["sh.600000"] + 0.01 * 1
        self.assertAlmostEqual(snap.fact_at("600000.SH", "debt_ratio", "2019-04-25"), first_quarter, places=5)


class Build(unittest.TestCase):
    def test_a_name_that_never_traded_in_the_window_is_skipped(self):
        bs = FakeBs(3, suspended={"sh.600001"})
        snap = src.build(bs, "2019-01-01", "2019-12-31")
        self.assertEqual(sorted(snap.prices), ["600000.SH", "600002.SH"])

    def test_the_snapshot_says_what_is_wrong_with_it(self):
        snap = src.build(FakeBs(2), "2019-01-01", "2019-12-31")
        self.assertEqual((snap.market, snap.universe), ("cn_a", "csi300"))
        text = " ".join(snap.limitations)
        for needle in ("half year", "delisted", "Sharia unknown", "does not move with the price", "back-adjusted"):
            self.assertIn(needle, text)

    def test_sectors_are_kept_only_when_the_source_gives_one(self):
        snap = src.build(FakeBs(3), "2019-01-01", "2019-12-31")
        self.assertEqual(snap.sectors, {"600001.SH": "J66货币金融服务"})


class EndToEnd(unittest.TestCase):
    """Fake service -> snapshot -> files -> engine -> Result."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        snap = src.build(FakeBs(6), "2019-01-01", "2019-12-31")
        cls.directory = Path(cls.tmp.name) / "snap"
        cls.version = store.write(snap, cls.directory)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def spec(self, **changes):
        out = {
            "spec_version": "1.0", "market": "cn_a", "universe": "csi300", "sharia": "off", "filters": [],
            "rank": [{"factor": "debt_ratio", "direction": "asc"}, {"factor": "dividend_yield", "direction": "desc"}],
            "top_k": 3, "n_drop": 1, "rebalance": "M", "period": {"start": "2019-03-01", "end": "2019-12-31"},
            "costs": {"fee_rate": 0.0015, "slip_rate": 0.005},
        }
        out.update(changes)
        return out

    def test_the_engine_runs_on_it_and_repeats_the_limits_of_the_data(self):
        result = run(self.spec(), store.load(self.directory), "q", NOW)
        self.assertEqual(len(result["rows"]), 3)
        self.assertEqual(result["receipt"]["data_version"], self.version)
        self.assertTrue(any(w.startswith("Data: Membership is the CSI 300 list") for w in result["warnings"]))
        self.assertTrue(all(row["sharia"] == "unknown" for row in result["rows"]))

    def test_the_lowest_debt_names_are_the_ones_held(self):
        snap = store.load(self.directory)
        result = run(self.spec(rank=[{"factor": "debt_ratio", "direction": "asc"}], n_drop=0), snap, "q", NOW)
        last = result["as_of"]
        debts = {r["symbol"]: snap.fact_at(r["symbol"], "debt_ratio", last) for r in result["rows"]}
        every = {s: snap.fact_at(s, "debt_ratio", last) for s in snap.prices}
        self.assertEqual(sorted(debts.values()), sorted(every.values())[:3])

    def test_sharia_compliant_only_returns_no_name_when_no_input_is_published(self):
        result = run(self.spec(sharia="compliant_only"), store.load(self.directory), "q", NOW)
        self.assertEqual(result["rows"], [])  # unknown is not compliant; nothing is guessed
        self.assertTrue(any(w.startswith("only 0 of 3") for w in result["warnings"]))

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is not installed")
    def test_both_results_satisfy_the_contract(self):
        for spec in (self.spec(), self.spec(sharia="compliant_only")):
            result = run(spec, store.load(self.directory), "q", NOW)
            self.assertEqual(list(validator(SIG_S).iter_errors(result)), [])


class Cli(unittest.TestCase):
    def test_a_failed_login_exits_2_and_writes_nothing(self):
        class Bs(FakeBs):
            def login(self):
                return Rs([], [], code="10001", msg="denied")

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(src.main(["--out", f"{tmp}/x"], bs=Bs(1)), 2)
            self.assertFalse(Path(tmp, "x").exists())

    def test_it_writes_a_snapshot_and_logs_out(self):
        class Bs(FakeBs):
            logged_out = False

            def logout(self):
                Bs.logged_out = True
                return Rs([], [])

        with tempfile.TemporaryDirectory() as tmp:
            code = src.main(["--out", f"{tmp}/snap", "--start", "2019-01-01", "--end", "2019-12-31", "--limit", "2"], bs=Bs(5))
            self.assertEqual(code, 0)
            self.assertEqual(len(store.load(f"{tmp}/snap").prices), 2)
            self.assertTrue(Bs.logged_out)


if __name__ == "__main__":
    unittest.main()
