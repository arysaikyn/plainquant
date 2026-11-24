import copy
import tempfile
import unittest
from pathlib import Path

from .. import store
from ..run import run
from ..verify import differences, verify
from .fixtures import make_snapshot, spec

STAMP = "2026-01-01T00:00:00Z"


class Verify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "snap"
        store.write(make_snapshot(n=12), self.dir)
        self.result = run(spec(), store.load(self.dir), "q", STAMP)

    def tearDown(self):
        self.tmp.cleanup()

    def test_an_untouched_result_reproduces(self):
        self.assertEqual(verify(self.result, str(self.dir)), (0, []))

    def test_an_edited_number_is_found_by_path(self):
        edited = copy.deepcopy(self.result)
        edited["backtest"]["metrics"]["sharpe"] += 0.01
        code, diff = verify(edited, str(self.dir))
        self.assertEqual((code, diff), (1, ["/backtest/metrics/sharpe"]))

    def test_another_snapshot_is_refused_not_compared(self):
        other = Path(self.tmp.name) / "other"
        store.write(make_snapshot(n=13), other)
        code, diff = verify(self.result, str(other))
        self.assertEqual(code, 2)
        self.assertIn("is not the receipt's", diff[0])

    def test_differences_reports_length_and_missing_keys(self):
        self.assertEqual(differences({"a": [1, 2]}, {"a": [1]}), ["/a (length 2 vs 1)"])
        self.assertEqual(differences({"a": 1}, {}), ["/a"])
