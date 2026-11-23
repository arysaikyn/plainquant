"""Golden vectors: the assertions of web/src/lib/gridcheck.test.ts, on the same
mulberry32 noise, so a failing case fails the same way in both languages."""

import unittest

from ..audit import exposure_of, grid_check, grid_block, persistence_of, returns_of


def _i32(x):
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x


def _imul(a, b):
    return _i32(_i32(a) * _i32(b))


def noise(seed, n, spread):
    state, out = seed, []
    for _ in range(n):
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = _imul(_i32(state) ^ (state >> 15), _i32(state) | 1)
        t = _i32(t ^ _i32(t + _imul(_i32(t) ^ ((t & 0xFFFFFFFF) >> 7), _i32(t) | 61)))
        out.append((((t ^ ((t & 0xFFFFFFFF) >> 14)) & 0xFFFFFFFF) / 0x100000000 - 0.5) * 2 * spread)
    return out


def curve_of(rets):
    out = [1.0]
    for r in rets:
        out.append(out[-1] * (1 + r))
    return out


CHOP = [abs(r) if i % 2 == 0 else -abs(r) for i, r in enumerate(noise(7, 60, 0.01))]
TREND = []
for shock in noise(11, 60, 0.01):
    TREND.append(0.3 * (TREND[-1] if TREND else 0.0) + shock)


class Returns(unittest.TestCase):
    def test_drops_broken_points(self):
        self.assertEqual([round(r, 6) for r in returns_of([1, 1.1, 0, 2])], [0.1])


class Exposure(unittest.TestCase):
    bench = curve_of(CHOP)

    def test_charges_a_curve_that_only_reads_the_size_of_the_move(self):
        harvest = curve_of([abs(r) * 0.5 - 0.0001 for r in CHOP])
        self.assertGreater(exposure_of(harvest, self.bench)["vol_share"], 0.6)

    def test_credits_a_curve_that_reads_the_direction(self):
        directional = curve_of([r * 0.8 for r in CHOP])
        self.assertLess(exposure_of(directional, self.bench)["vol_share"], 0.35)

    def test_refuses_to_guess_from_fewer_than_eight_observations(self):
        self.assertIsNone(exposure_of([1, 1.01, 1.02], [1, 1.01, 1.02]))


class Persistence(unittest.TestCase):
    def test_a_stop_hurts_on_a_mean_reverting_path(self):
        p = persistence_of(curve_of(CHOP))
        self.assertLess(p["gamma1"], 0)
        self.assertEqual(p["stop"], "hurts")

    def test_a_stop_adds_on_a_persistent_path(self):
        p = persistence_of(curve_of(TREND))
        self.assertGreater(p["gamma1"], 0)
        self.assertEqual(p["stop"], "adds")


class Check(unittest.TestCase):
    def test_fails_a_price_only_rule_set_that_names_no_exit(self):
        r = grid_check(["price", "volume"], rank_exit=False)
        self.assertEqual(r["verdict"], "gridlike")
        self.assertGreaterEqual(r["score"], 55)
        self.assertEqual([f["id"] for f in r["findings"]], ["noExitPolicy", "priceOnly", "shortDecay"])

    def test_passes_a_fundamental_rule_set_that_exits_by_rank(self):
        r = grid_check(["fundamental"], rank_exit=True)
        self.assertEqual(
            r,
            {
                "score": 0,
                "verdict": "crossSection",
                "families": ["fundamental"],
                "findings": [],
                "exposure": None,
                "persistence": None,
            },
        )

    def test_collapses_duplicate_families(self):
        self.assertEqual(
            grid_check(["price", "price"], rank_exit=True)["score"], grid_check(["price"], rank_exit=True)["score"]
        )

    def test_charges_turnover_and_concentration_against_the_caps(self):
        idle = grid_check(["fundamental"], True, turnover=0.3, max_weight=0.05)
        churn = grid_check(["fundamental"], True, turnover=1.4, max_weight=0.24)
        self.assertEqual(idle["score"], 0)
        self.assertEqual([f["id"] for f in churn["findings"]], ["highTurnover", "concentrated"])

    def test_adds_the_measured_findings_on_top_of_the_structural_ones(self):
        r = grid_check(
            ["momentum"],
            True,
            curve=curve_of([abs(x) * 0.5 + 0.0002 for x in CHOP]),
            bench=curve_of(CHOP),
        )
        self.assertEqual([f["id"] for f in r["findings"]], ["priceOnly", "shortDecay", "volHarvest"])
        self.assertEqual(r["verdict"], "gridlike")

    def test_the_contract_block_is_in_range(self):
        block = grid_block(grid_check(["momentum"], True, curve=curve_of(CHOP), bench=curve_of(CHOP)))
        self.assertTrue(0 <= block["path_exposure"] <= 1)
        self.assertTrue(-1 <= block["persistence"] <= 1)


if __name__ == "__main__":
    unittest.main()
