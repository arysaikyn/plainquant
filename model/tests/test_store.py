import json
import tempfile
import unittest
from pathlib import Path

from .. import store
from ..run import run
from .fixtures import make_snapshot, spec

NOW = "2026-01-01T00:00:00Z"


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "snap"
        self.snap = make_snapshot(n=12)
        self.version = store.write(self.snap, self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_round_trip_gives_the_same_result_and_the_manifest_version(self):
        loaded = store.load(self.dir)
        self.assertEqual(loaded.version, self.version)
        a = run(spec(), self.snap, "q", NOW)
        b = run(spec(), loaded, "q", NOW)
        self.assertEqual(b["receipt"]["data_version"], self.version)
        a["receipt"]["data_version"] = b["receipt"]["data_version"]
        self.assertEqual(a, b)  # float repr round-trips, so nothing moved

    def test_the_market_survives_the_round_trip_and_is_part_of_the_version(self):
        self.assertEqual(store.load(self.dir).market, "cn_a")
        other = store.write(make_snapshot(n=12, market="us"), Path(self.tmp.name) / "us")
        self.assertNotEqual(other, self.version)

    def test_the_known_limits_of_the_data_survive_and_change_the_version(self):
        s = make_snapshot(n=12)
        s.limitations = ["Universe is today's list."]
        version = store.write(s, Path(self.tmp.name) / "lim")
        self.assertNotEqual(version, self.version)
        self.assertEqual(store.load(Path(self.tmp.name) / "lim").limitations, ["Universe is today's list."])
        self.assertEqual(store.load(self.dir).limitations, [])

    def test_a_name_that_left_the_index_and_came_back_keeps_both_stays(self):
        s = make_snapshot(n=12)
        s.membership["S000"] = [("2019-01-01", "2020-06-30"), ("2021-01-04", None)]
        store.write(s, Path(self.tmp.name) / "gap")
        loaded = store.load(Path(self.tmp.name) / "gap")
        self.assertEqual(loaded.membership["S000"], [("2019-01-01", "2020-06-30"), ("2021-01-04", None)])
        self.assertIn("S000", loaded.universe_at("2020-03-02"))
        self.assertNotIn("S000", loaded.universe_at("2020-09-01"))
        self.assertIn("S000", loaded.universe_at("2021-02-01"))

    def test_an_older_manifest_format_is_refused(self):
        self._retouch("dates.csv", lambda t: t)  # keep the files consistent with the manifest
        path = self.dir / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["format"] = 1
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "unsupported snapshot format"):
            store.load(self.dir)

    def test_the_same_content_in_another_directory_has_the_same_version(self):
        self.assertEqual(store.write(self.snap, Path(self.tmp.name) / "other"), self.version)

    def test_one_changed_price_changes_the_version(self):
        s = make_snapshot(n=12)
        s.prices["S000"]["2020-03-03"] *= 1.0001
        self.assertNotEqual(store.write(s, Path(self.tmp.name) / "moved"), self.version)

    def test_editing_a_file_after_the_fact_is_refused(self):
        path = self.dir / "prices.csv"
        path.write_text(path.read_text().replace("S000,2020-03-03,", "S000,2020-03-03,9", 1))
        with self.assertRaisesRegex(ValueError, "prices.csv does not match"):
            store.load(self.dir)

    def _retouch(self, name, fn):
        """Change a file and fix the manifest, as a careless adapter would."""
        import hashlib

        path = self.dir / name
        path.write_text(fn(path.read_text()))
        m = json.loads((self.dir / "manifest.json").read_text())
        m["files"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
        (self.dir / "manifest.json").write_text(json.dumps(m))

    def test_a_fact_without_an_announcement_date_is_refused(self):
        self._retouch("facts.csv", lambda t: t.replace("S000,2019-04-30,", "S000,,", 1))
        with self.assertRaisesRegex(ValueError, "no announcement date"):
            store.load(self.dir)

    def test_a_non_positive_price_is_refused(self):
        self._retouch("prices.csv", lambda t: t.replace("S000,2020-03-03,", "S000,2020-03-03,-", 1))
        with self.assertRaisesRegex(ValueError, "non-positive close"):
            store.load(self.dir)

    def test_an_unpublished_fact_loads_as_none_not_zero(self):
        loaded = store.load(self.dir)
        missing = [
            (s, d)
            for s, rows in self.snap.facts.items()
            for d, row in rows
            if row["receivables_ratio"] is None
        ]
        self.assertTrue(missing)
        s, d = missing[0]
        self.assertIsNone(loaded.fact_at(s, "receivables_ratio", d))


if __name__ == "__main__":
    unittest.main()
