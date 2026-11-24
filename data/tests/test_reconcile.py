import random
import unittest

from data import reconcile as rec


def series(returns, start=100.0):
    out = [start]
    for r in returns:
        out.append(out[-1] * (1 + r))
    return out


DATES = [f"2020-{m:02d}-28" for m in range(1, 13)] + [f"2021-{m:02d}-28" for m in range(1, 13)]


class Compare(unittest.TestCase):
    def setUp(self):
        rng = random.Random(3)
        self.market = [rng.gauss(0.008, 0.04) for _ in range(len(DATES) - 1)]
        self.index = dict(zip(DATES, series(self.market, 4000.0)))

    def test_a_curve_that_follows_the_market_passes(self):
        close = [r * 0.9 + 0.001 for r in self.market]  # same moves, a little less, plus a little yield
        got = rec.compare(DATES, series(close, 1.0), self.index)
        self.assertGreater(got["correlation"], 0.99)
        self.assertTrue(got["ok"])

    def test_a_curve_with_the_dates_shifted_fails_on_correlation(self):
        shifted = self.market[3:] + self.market[:3]  # right returns, wrong months
        got = rec.compare(DATES, series(shifted, 1.0), self.index)
        self.assertLess(got["correlation"], rec.MIN_CORRELATION)
        self.assertFalse(got["ok"])

    def test_a_curve_that_tracks_but_drifts_far_apart_fails_on_the_gap(self):
        drifting = [r + 0.02 for r in self.market]  # 24 points a year too high, same shape
        got = rec.compare(DATES, series(drifting, 1.0), self.index)
        self.assertGreater(got["correlation"], 0.99)
        self.assertGreater(got["gap"], rec.MAX_ANNUAL_GAP)
        self.assertFalse(got["ok"])

    def test_an_index_with_no_close_before_the_first_day_is_refused(self):
        with self.assertRaises(ValueError):
            rec.compare(["2019-01-01", "2020-01-28"], [1.0, 1.1], {"2020-02-28": 100.0})


if __name__ == "__main__":
    unittest.main()
