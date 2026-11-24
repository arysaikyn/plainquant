"""The ask path, with a scripted model and a synthetic snapshot. No key, no network."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import app
import engine
from model.tests.fixtures import make_snapshot, spec

SNAP = make_snapshot(n=30)
SNAP_SPEC = spec(universe="synthetic", market="cn_a")


def scripted(*replies):
    """A model that answers from a list, then repeats its last answer."""
    asked = []

    def complete(messages):
        asked.append(messages)
        return replies[min(len(asked), len(replies)) - 1]

    complete.asked = asked
    return complete


CLAIMS = json.dumps({"claims": ["Annual return was {backtest.metrics.annual_return}", "It beat the market by 5%"]})


class Ask(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.signals = Path(self.tmp.name) / "signals.json"
        self.client = TestClient(app.app)
        self.patches = [mock.patch.object(app, "SIGNALS_PATH", self.signals), mock.patch.object(engine, "get_snapshot", lambda: SNAP)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def post(self, question, provider):
        with mock.patch.object(engine, "get_provider", lambda: provider):
            return self.client.post("/api/engine/ask", json={"question": question})

    def test_a_question_becomes_a_run_and_an_explanation_and_the_latest_run_is_saved(self):
        r = self.post("cheap low debt names", scripted(json.dumps(SNAP_SPEC), CLAIMS))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["result"]["spec"], SNAP_SPEC)
        self.assertEqual(body["result"]["query"], "cheap low debt names")
        self.assertEqual(json.loads(self.signals.read_text()), body["result"])  # /run shows this run
        self.assertEqual(len(body["claims"]), 1)  # the sentence with its own digit was dropped
        self.assertEqual(body["claims"][0][1]["ref"], "backtest.metrics.annual_return")
        self.assertEqual(body["dropped"], 1)

    def test_a_request_for_advice_is_refused_and_nothing_is_run_or_saved(self):
        r = self.post("which stock should I buy?", scripted('{"refuse": "advice"}'))
        self.assertEqual((r.status_code, r.json()), (200, {"refusal": "advice"}))
        self.assertFalse(self.signals.exists())

    def test_a_model_that_cannot_write_a_valid_spec_is_a_422_with_the_problems(self):
        r = self.post("something", scripted(json.dumps({**SNAP_SPEC, "stop_loss": 0.05})))
        self.assertEqual(r.status_code, 422)
        self.assertTrue(r.json()["problems"])
        self.assertFalse(self.signals.exists())

    def test_the_explanation_failing_does_not_lose_the_run(self):
        class Flaky:
            calls = 0

            def __call__(self, messages):
                Flaky.calls += 1
                if Flaky.calls == 1:
                    return json.dumps(SNAP_SPEC)
                raise engine.ProviderError("model service answered 529")

        r = self.post("cheap", Flaky())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["claims"], [])
        self.assertIn("529", r.json()["claims_error"])
        self.assertTrue(self.signals.exists())

    def test_without_a_key_it_says_so(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
                r = self.client.post("/api/engine/ask", json={"question": "cheap"})
        self.assertEqual(r.status_code, 503)
        self.assertIn("ANTHROPIC_API_KEY", r.json()["detail"])

    def test_a_provider_failure_is_a_502_without_the_key_in_it(self):
        def broken(messages):
            raise engine.ProviderError("model service answered 401")

        r = self.post("cheap", broken)
        self.assertEqual(r.status_code, 502)
        self.assertNotIn("sk-", r.text)

    def test_a_bad_question_is_a_422(self):
        for body in ({"question": ""}, {"question": "x" * 501}, {"question": 5}, {"nope": 1}, [1]):
            r = self.client.post("/api/engine/ask", json=body)
            self.assertEqual(r.status_code, 422, body)

    def test_a_missing_snapshot_is_a_503(self):
        def missing():
            raise engine.NotConfigured("no usable snapshot at /x: FileNotFoundError")

        with mock.patch.object(engine, "get_snapshot", missing):
            r = self.post("cheap", scripted("{}"))
        self.assertEqual(r.status_code, 503)

    def test_the_prompt_the_model_sees_lists_the_snapshot_universe_and_market(self):
        provider = scripted('{"refuse": "advice"}')
        self.post("anything", provider)
        system = provider.asked[0][0]["content"]
        self.assertIn("synthetic (market cn_a)", system)

    def test_the_provider_reads_the_key_from_the_environment_only(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            with self.assertRaises(engine.NotConfigured):
                engine.get_provider()
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            self.assertTrue(callable(engine.get_provider()))

    def test_the_provider_sends_the_system_text_apart_and_returns_the_text(self):
        class Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"content": [{"type": "text", "text": "hello"}, {"type": "tool_use"}]}

        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}), mock.patch.object(engine.httpx, "post", return_value=Resp) as post:
            out = engine.get_provider()([{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}])
        sent = post.call_args.kwargs
        self.assertEqual(out, "hello")
        self.assertEqual((sent["json"]["system"], sent["json"]["messages"]), ("S", [{"role": "user", "content": "Q"}]))
        self.assertEqual(sent["headers"]["x-api-key"], "sk-test")

    def test_a_non_200_from_the_model_service_becomes_a_provider_error_without_the_body(self):
        class Resp:
            status_code = 401
            text = "invalid x-api-key: sk-test"

        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}), mock.patch.object(engine.httpx, "post", return_value=Resp):
            with self.assertRaises(engine.ProviderError) as caught:
                engine.get_provider()([{"role": "user", "content": "Q"}])
        self.assertNotIn("sk-test", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
