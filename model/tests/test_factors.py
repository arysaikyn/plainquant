"""Each price factor against a value worked out by hand, on a series built to make that easy."""

import statistics
import unittest

from ..factors import REGISTRY, factor
from ..snapshot import Snapshot
from .fixtures import weekdays
from datetime import date


def snapshot(prices_of, n=400):
    days = weekdays(date(2019, 1, 1), date(2021, 12, 31))[:n]
    series = {d: prices_of(i) for i, d in enumerate(days)}
    return Snapshot(
        version="t", universe="u", market="cn_a", dates=days, prices={"A": series}, facts={"A": []},
        membership={"A": [(days[0], None)]},
    ), days


class PriceFactors(unittest.TestCase):
    def test_a_steady_climb_gives_the_compound_change_of_each_window(self):
        snap, days = snapshot(lambda i: 100 * 1.001**i)
        d = days[300]
        self.assertAlmostEqual(factor("momentum_6m").read(snap, "A", d), 1.001**126 - 1, places=12)
        self.assertAlmostEqual(factor("return_1m").read(snap, "A", d), 1.001**21 - 1, places=12)
        self.assertAlmostEqual(factor("momentum_12_1").read(snap, "A", d), 1.001**(252 - 21) - 1, places=12)

    def test_momentum_12_1_leaves_the_last_month_out(self):
        # Flat for a year, then a jump in the last month: 12-1 must not see it, 1m must.
        snap, days = snapshot(lambda i: 100.0 if i < 290 else 150.0)
        d = days[299]
        self.assertEqual(factor("momentum_12_1").read(snap, "A", d), 0.0)
        self.assertAlmostEqual(factor("return_1m").read(snap, "A", d), 0.5)

    def test_volatility_is_the_sample_deviation_of_the_last_sixty_returns(self):
        steps = lambda i: 1.01 if i % 2 else 0.99
        level = {}
        def prices_of(i):
            level[i] = 100.0 if i == 0 else level[i - 1] * steps(i)
            return level[i]
        snap, days = snapshot(prices_of)
        d = days[200]
        window = [level[i] / level[i - 1] - 1 for i in range(141, 201)]
        self.assertAlmostEqual(factor("volatility_60d").read(snap, "A", d), statistics.stdev(window), places=12)
        self.assertEqual(len(window), 60)

    def test_a_constant_return_has_no_volatility(self):
        snap, days = snapshot(lambda i: 100 * 1.001**i)
        self.assertAlmostEqual(factor("volatility_60d").read(snap, "A", days[200]), 0.0, places=12)

    def test_no_value_without_enough_history(self):
        snap, days = snapshot(lambda i: 100 * 1.001**i)
        self.assertIsNone(factor("momentum_6m").read(snap, "A", days[100]))
        self.assertIsNone(factor("momentum_12_1").read(snap, "A", days[200]))
        self.assertIsNone(factor("return_1m").read(snap, "A", days[10]))
        self.assertIsNone(factor("volatility_60d").read(snap, "A", days[30]))

    def test_a_value_never_uses_a_price_after_its_date(self):
        snap, days = snapshot(lambda i: 100 * 1.001**i)
        before = {f: factor(f).read(snap, "A", days[300]) for f in ("momentum_6m", "momentum_12_1", "return_1m", "volatility_60d")}
        for d in days[301:]:
            snap.prices["A"][d] *= 7
        snap.__post_init__()
        after = {f: factor(f).read(snap, "A", days[300]) for f in before}
        self.assertEqual(before, after)

    def test_every_price_factor_names_a_known_family(self):
        self.assertEqual({f: REGISTRY[f].family for f in ("momentum_6m", "momentum_12_1", "return_1m", "volatility_60d")},
                         {"momentum_6m": "momentum", "momentum_12_1": "momentum", "return_1m": "reversal", "volatility_60d": "volatility"})


if __name__ == "__main__":
    unittest.main()
