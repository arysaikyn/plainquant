import json
import unittest

from model.run import run
from model.tests.fixtures import make_snapshot, spec as base_spec

from .. import claims as claims_mod
from ..evaluate import contains, evaluate, load_cases
from ..spec import REFUSALS, extract_json, problems, question_to_spec, system_prompt
from ..spec import Draft202012Validator

UNIVERSES = {"synthetic": "cn_a"}
TODAY = "2026-11-23"


def scripted(*replies):
    """A model that answers from a list and remembers what it was asked."""
    asked = []

    def complete(messages):
        asked.append(json.loads(json.dumps(messages)))
        return replies[min(len(asked), len(replies)) - 1]

    complete.asked = asked
    return complete


GOOD = json.dumps(base_spec())


class ExtractJson(unittest.TestCase):
    def test_reads_an_object_out_of_prose_and_fences(self):
        self.assertEqual(extract_json('Sure!\n```json\n{"a": 1}\n```\nDone.'), {"a": 1})

    def test_an_escaped_quote_does_not_end_the_string(self):
        self.assertEqual(extract_json(r'{"a": "say \"hi\" }", "b": 2}'), {"a": 'say "hi" }', "b": 2})

    def test_nested_objects_and_a_leading_broken_brace(self):
        self.assertEqual(extract_json('{ oops {"a": {"b": 1}}'), {"a": {"b": 1}})

    def test_no_object_is_none(self):
        for text in ("", "no json here", "[1, 2]", '{"a": '):
            self.assertIsNone(extract_json(text))


@unittest.skipIf(Draft202012Validator is None, "jsonschema is not installed")
class QuestionToSpec(unittest.TestCase):
    def test_a_valid_first_reply_is_accepted(self):
        out = question_to_spec("q", scripted(GOOD), UNIVERSES, TODAY)
        self.assertTrue(out.ok)
        self.assertEqual((out.attempts, out.spec), (1, base_spec()))

    def test_a_stop_loss_is_fed_back_and_the_second_reply_is_taken(self):
        model = scripted(json.dumps(base_spec(stop_loss=0.05)), GOOD)
        out = question_to_spec("q", model, UNIVERSES, TODAY)
        self.assertTrue(out.ok)
        self.assertEqual(out.attempts, 2)
        feedback = model.asked[1][-1]["content"]
        self.assertIn("stop_loss", feedback)

    def test_a_model_that_never_gets_it_right_fails_after_three_tries(self):
        out = question_to_spec("q", scripted(json.dumps(base_spec(stop_loss=1))), UNIVERSES, TODAY)
        self.assertFalse(out.ok)
        self.assertEqual(out.attempts, 3)
        self.assertTrue(out.problems)

    def test_a_reply_with_no_json_is_a_problem_not_a_crash(self):
        out = question_to_spec("q", scripted("I think you should buy.", GOOD), UNIVERSES, TODAY)
        self.assertTrue(out.ok)
        self.assertEqual(out.attempts, 2)

    def test_an_unregistered_factor_is_named_with_the_choices(self):
        bad = base_spec(rank=[{"factor": "vibes", "direction": "desc"}])
        self.assertIn("vibes", problems(bad)[0])
        self.assertIn("debt_ratio", problems(bad)[0])

    def test_a_universe_the_snapshot_set_does_not_carry_is_refused(self):
        self.assertTrue(problems(base_spec(universe="csi300"), UNIVERSES))
        self.assertTrue(problems(base_spec(market="us"), UNIVERSES))
        self.assertEqual(problems(base_spec(), UNIVERSES), [])

    def test_each_refusal_the_product_names_is_accepted_and_nothing_else(self):
        for rule in REFUSALS:
            out = question_to_spec("q", scripted(json.dumps({"refuse": rule})), UNIVERSES, TODAY)
            self.assertEqual((out.refusal, out.spec, out.attempts), (rule, None, 1))
        out = question_to_spec("q", scripted(json.dumps({"refuse": "vibes"})), UNIVERSES, TODAY)
        self.assertIsNone(out.refusal)
        self.assertFalse(out.ok)

    def test_the_prompt_carries_the_closed_vocabulary_and_the_boundary(self):
        text = system_prompt(UNIVERSES, TODAY)
        for needle in ("debt_ratio", "momentum_6m", "synthetic (market cn_a)", TODAY, "no stop-loss", '"refuse"'):
            self.assertIn(needle, text)


class Claims(unittest.TestCase):
    result = run(base_spec(), make_snapshot(), "q", "2026-01-01T00:00:00Z")

    def segs(self, sentence):
        return claims_mod.segments(sentence, self.result)

    def test_a_slot_takes_its_value_from_the_result(self):
        out = self.segs("The Sharpe ratio was {backtest.metrics.sharpe} over the period")
        self.assertEqual(
            out,
            [
                {"text": "The Sharpe ratio was "},
                {"ref": "backtest.metrics.sharpe", "value": self.result["backtest"]["metrics"]["sharpe"]},
                {"text": " over the period"},
            ],
        )

    def test_paths_reach_rows_receipt_and_audit(self):
        for path in ("rows.0.symbol", "receipt.spec_hash", "audit.grid.verdict", "as_of", "spec.top_k"):
            self.assertIsInstance(self.segs("see {%s} here" % path), list, path)

    def test_a_digit_the_model_wrote_is_refused_in_every_script(self):
        for sentence in ("It returned 12% a year", "عائد ١٢ بالمئة", "收益 ３ 倍", "gain {as_of} then 7 more", "ends with 3"):
            self.assertEqual(self.segs(sentence), "carries a number of its own", sentence)

    def test_a_slot_that_names_nothing_is_refused(self):
        self.assertIn("names nothing", self.segs("It returned {backtest.metrics.alpha}"))
        self.assertIn("names nothing", self.segs("It returned {backtest.metrics}"))  # an object is not a value
        self.assertIn("names nothing", self.segs("{rows.999.symbol} led"))

    def test_malformed_and_empty_sentences_are_refused(self):
        self.assertEqual(self.segs("broken {slot"), "has an unclosed slot")
        self.assertEqual(self.segs("{backtest.metrics.sharpe}"), "says nothing")

    def test_the_pipeline_keeps_the_good_sentences_and_reports_the_rest(self):
        reply = json.dumps(
            {
                "claims": [
                    "Annual return was {backtest.metrics.annual_return}",
                    "It beat the market by 5%",
                    "The grid verdict was {audit.grid.verdict}",
                    42,
                ]
            }
        )
        out = claims_mod.result_to_claims(self.result, scripted(reply))
        self.assertEqual(len(out.claims), 2)
        self.assertEqual([reason for _, reason in out.dropped], ["carries a number of its own", "is not a sentence"])

    def test_a_reply_that_is_not_claims_yields_nothing(self):
        for reply in ("no json", '{"claims": "one string"}', "{}"):
            self.assertEqual(claims_mod.result_to_claims(self.result, scripted(reply)).claims, [])


class Evaluate(unittest.TestCase):
    cases = load_cases()

    def test_contains_matches_lists_as_sets_and_dicts_as_subsets(self):
        self.assertTrue(contains({"a": [{"x": 1}]}, {"a": [{"x": 1, "y": 2}, {"x": 3}], "b": 0}))
        self.assertFalse(contains({"a": [{"x": 9}]}, {"a": [{"x": 1}]}))
        self.assertFalse(contains({"a": 1}, {"b": 1}))

    def test_the_set_covers_three_languages_and_at_least_30_questions(self):
        self.assertGreaterEqual(len(self.cases), 30)
        text = "".join(c["question"] for c in self.cases)
        self.assertTrue(any("\u4e00" <= ch <= "\u9fff" for ch in text))
        self.assertTrue(any("\u0600" <= ch <= "\u06ff" for ch in text))

    def test_every_case_is_one_of_the_two_shapes_and_the_set_covers_the_refusals(self):
        for case in self.cases:
            self.assertEqual(sum(k in case for k in ("expect", "refuse")), 1, case["question"])
        self.assertEqual({c["refuse"] for c in self.cases if "refuse" in c}, set(REFUSALS))

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is not installed")
    def test_a_perfect_model_scores_everything_and_a_silent_one_scores_nothing(self):
        # The perfect model answers each case with exactly what the case expects.
        by_question = {
            c["question"]: ({"refuse": c["refuse"]} if "refuse" in c else base_spec(**c["expect"])) for c in self.cases
        }

        def perfect(messages):
            return json.dumps(by_question[messages[1]["content"]])

        good = evaluate(self.cases, perfect, UNIVERSES, TODAY)
        asked = sum("expect" in c for c in self.cases)
        refused = sum("refuse" in c for c in self.cases)
        self.assertEqual((good["valid"], good["correct"], good["refusals_correct"]), (asked, asked, refused))
        self.assertEqual(good["failures"], [])
        bad = evaluate(self.cases, lambda m: "no idea", UNIVERSES, TODAY)
        self.assertEqual((bad["valid"], bad["correct"], bad["refusals_correct"]), (0, 0, 0))
        self.assertEqual(len(bad["failures"]), len(self.cases))


if __name__ == "__main__":
    unittest.main()
