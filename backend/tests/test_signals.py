import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

import app


class EngineSignalsRouteTest(unittest.TestCase):
    def test_serves_the_latest_run_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "signals.json"
            path.write_text(json.dumps({"schema_version": "1.2"}))
            with mock.patch.object(app, "SIGNALS_PATH", path):
                response = asyncio.run(app.signals())
        self.assertEqual(response.media_type, "application/json")
        self.assertEqual(json.loads(response.body), {"schema_version": "1.2"})

    def test_is_a_404_until_the_engine_has_written_a_run(self):
        with mock.patch.object(app, "SIGNALS_PATH", Path("/nonexistent/signals.json")):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(app.signals())
        self.assertEqual(caught.exception.status_code, 404)

    def test_the_path_comes_from_the_environment_never_the_request(self):
        self.assertEqual(app.SIGNALS_PATH.name, "signals.json")
        self.assertEqual(app.SIGNALS_PATH.parent.name, "model")

    def test_the_ai_proxy_still_refuses_the_engine_path(self):
        with self.assertRaises(HTTPException):
            app.upstream_path("engine/signals")


if __name__ == "__main__":
    unittest.main()
