"""On pure noise the audit must stay quiet. Measured 2026-11-23, 120 noise datasets of 25
names: before the significance gates `stopHurts` fired in 52% of runs and a basic fundamental
spec read as a cross-section in 44%; after, 2% and 93%. This pins it on a smaller sample."""

import collections
import unittest

from ..run import run
from .fixtures import make_snapshot, spec

NOW = "2026-01-01T00:00:00Z"
RUNS = 60


class NoiseIsQuiet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.findings, cls.verdicts = collections.Counter(), collections.Counter()
        for seed in range(RUNS):
            grid = run(spec(top_k=8, n_drop=2), make_snapshot(seed=seed, n=20), "q", NOW)["audit"]["grid"]
            cls.verdicts[grid["verdict"]] += 1
            cls.findings.update(f["id"] for f in grid["findings"])

    def test_stop_hurts_is_rare_on_noise(self):
        self.assertLessEqual(self.findings["stopHurts"], 0.10 * RUNS)  # was about 50% before the gate

    def test_vol_harvest_is_rare_on_noise(self):
        self.assertLessEqual(self.findings["volHarvest"], 0.10 * RUNS)

    def test_a_fundamental_rank_exit_spec_is_never_called_a_grid_on_noise(self):
        self.assertEqual(self.verdicts["gridlike"], 0)

    def test_most_noise_runs_read_as_a_cross_section(self):
        self.assertGreaterEqual(self.verdicts["crossSection"], 0.7 * RUNS)  # was 44% before the gate


if __name__ == "__main__":
    unittest.main()
