import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from .. import store
from ..__main__ import main
from ..run import run
from .fixtures import make_snapshot, spec
from .test_contract import SIG_S, Draft202012Validator, validator

STAMP = "2026-01-01T00:00:00Z"


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.snap_dir = root / "snap"
        self.version = store.write(make_snapshot(n=12), self.snap_dir)
        self.spec_path = root / "spec.json"
        self.spec_path.write_text(json.dumps(spec()))
        self.out = root / "signals.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_the_result_the_engine_returns_for_the_stored_snapshot(self):
        code = main([str(self.spec_path), str(self.snap_dir), "--query", "q", "-o", str(self.out), "--generated-at", STAMP])
        self.assertEqual(code, 0)
        written = json.loads(self.out.read_text())
        self.assertEqual(written, run(spec(), store.load(self.snap_dir), "q", STAMP))
        self.assertEqual(written["receipt"]["data_version"], self.version)

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is not installed")
    def test_what_it_writes_satisfies_the_contract(self):
        main([str(self.spec_path), str(self.snap_dir), "--query", "q", "-o", str(self.out)])
        self.assertEqual(list(validator(SIG_S).iter_errors(json.loads(self.out.read_text()))), [])

    def test_a_spec_the_engine_refuses_exits_2_and_writes_nothing(self):
        self.spec_path.write_text(json.dumps(spec(stop_loss=0.05)))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main([str(self.spec_path), str(self.snap_dir), "--query", "q", "-o", str(self.out)])
        self.assertEqual(code, 2)
        self.assertIn("does not define", err.getvalue())
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
