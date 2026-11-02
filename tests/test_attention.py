import asyncio
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from experiment_lab.analysis import artifacts, measures
from experiment_lab.cli import load_scenario
from experiment_lab.engine import Engine
from experiment_lab.scenario import validate
from experiment_lab.storage import Run, read, write
from experiment_lab.suite import prepare, run_suite, score, validate_expectations, verified_plan

ROOT = Path(__file__).resolve().parents[1]


class AttentionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def scenario(self, scheduling="staggered"):
        return validate({"schema": "agent-experiment-lab.scenario/1", "label": "Attention fixture",
            "participants": {p: {"label": p, "kind": "protocol_fixture", "role_instructions": f"Private role for {p}"} for p in ("one", "two")},
            "rooms": {"room": {"members": ["one", "two"], "type": "direct"}},
            "attention": {"policy": "selective", "scheduling": scheduling},
            "steps": [{"action": "message", "room": "room", "speaker": "one", "text": "Can someone answer this?", "provenance": "operator_authored_fixture"},
                      {"action": "round", "room": "room", "participants": ["one", "two"], "private_context": {"one": "Only one may see this"}}],
            "limits": {"turn_seconds": 2}})

    def bindings(self):
        return {"schema": "agent-experiment-lab.bindings/1", "participants": {p: {"command": [sys.executable, str(ROOT / "tests/fixtures/acp_agent.py"), "--home", str(self.home / p), "--mode", "after_peer"], "cwd": str(self.home)} for p in ("one", "two")}}

    def run_engine(self, scenario):
        run = Run.create(self.home / "run", scenario, self.bindings())
        with run.lock():
            asyncio.run(Engine(run).execute())
        return run

    def test_staggering_supplies_visible_answer_then_agent_itself_passes(self):
        run = self.run_engine(self.scenario())
        self.assertEqual([turn["delivery"] for turn in run.data["turns"]], ["delivered", "no_response"])
        self.assertEqual(measures(run)["social"]["contributions"], 1)
        self.assertEqual(measures(run)["social"]["scripted_context_messages"], 1)
        second = read(run.path / run.data["turns"][1]["input"]["path"])["prompt"]
        context = json.loads(second.split("\n\n", 1)[1])
        self.assertEqual(context["history"][-1]["speaker"], "one")
        self.assertNotIn("Only one may see this", second)
        self.assertNotIn("Private role for one", second)
        self.assertIn("Private role for two", second)

    def test_parallel_condition_has_same_snapshot_and_no_artificial_silence(self):
        run = self.run_engine(self.scenario("simultaneous"))
        self.assertEqual([turn["delivery"] for turn in run.data["turns"]], ["delivered", "delivered"])
        contexts = [json.loads(read(run.path / turn["input"]["path"])["prompt"].split("\n\n", 1)[1]) for turn in run.data["turns"]]
        self.assertEqual(contexts[0]["history"], contexts[1]["history"])

    def test_recheck_keeps_parallel_drafts_but_agent_reconsiders_with_public_answer(self):
        run = self.run_engine(self.scenario("recheck"))
        self.assertEqual(sorted(t["delivery"] for t in run.data["turns"]), ["delivered", "no_response"])
        checked = [t for t in run.data["turns"] if t.get("publication_check")]
        self.assertEqual(len(checked), 1)
        check = checked[0]["publication_check"]
        self.assertEqual(check["original_decision"]["action"], "speak")
        self.assertEqual(check["decision"]["action"], "pass")
        original = [json.loads(read(run.path / t["input"]["path"])["prompt"].split("\n\n", 1)[1]) for t in run.data["turns"]]
        self.assertEqual(original[0]["history"], original[1]["history"])
        updated = json.loads(read(run.path / check["input"]["path"])["prompt"].split("\n\n", 1)[1])
        self.assertEqual(len(updated["history"]), 2)
        self.assertEqual(updated["publication_review"]["your_private_draft"]["action"], "speak")
        before = [(self.home / p / "requests.jsonl").read_text() for p in ("one", "two")]
        asyncio.run(Engine(run).execute())
        self.assertEqual(before, [(self.home / p / "requests.jsonl").read_text() for p in ("one", "two")])

    def test_recheck_budget_does_not_invent_a_pass_or_publish_unchecked_draft(self):
        scenario = self.scenario("recheck")
        scenario["limits"]["max_turns"] = 2
        run = self.run_engine(scenario)
        self.assertEqual(run.data["status"], "limited")
        self.assertEqual(sum(t["delivery"] == "delivered" for t in run.data["turns"]), 1)
        self.assertEqual(sum(t["delivery"] == "pending" for t in run.data["turns"]), 1)
        self.assertFalse(any(t["delivery"] == "no_response" for t in run.data["turns"]))

    def test_recheck_interruption_withholds_every_stale_draft(self):
        scenario = self.scenario("recheck")
        scenario["steps"][0] = {"action": "cue", "room": "room", "text": "INTERRUPT now"}
        scenario["steps"][1]["interrupt"] = {"participant": "one", "when": "first_chunk", "text": "REVISED stop this request"}
        bindings = self.bindings()
        bindings["participants"]["two"]["command"][-1] = "quick"
        run = Run.create(self.home / "run", validate(scenario), bindings)
        asyncio.run(Engine(run).execute())
        self.assertTrue(all(t["delivery"] == "not_delivered" for t in run.data["turns"]))
        self.assertFalse(any(t.get("publication_check") for t in run.data["turns"]))

    def test_failed_publication_check_cannot_publish_or_replay(self):
        bindings = self.bindings()
        for endpoint in bindings["participants"].values():
            endpoint["command"][-1] = "recheck_disconnect"
        run = Run.create(self.home / "run", self.scenario("recheck"), bindings)
        asyncio.run(Engine(run).execute())
        self.assertEqual(run.data["status"], "needs_resolution")
        self.assertEqual(sum(t["delivery"] == "delivered" for t in run.data["turns"]), 1)
        self.assertEqual(sum(t["delivery"] == "uncertain" for t in run.data["turns"]), 1)
        before = [(self.home / p / "requests.jsonl").read_text() for p in ("one", "two")]
        asyncio.run(Engine(run).execute())
        self.assertEqual(before, [(self.home / p / "requests.jsonl").read_text() for p in ("one", "two")])

    def test_cancelled_staggered_turn_is_not_a_voluntary_pass(self):
        scenario = self.scenario()
        scenario["steps"][0] = {"action": "cue", "room": "room", "text": "INTERRUPT now"}
        scenario["steps"][1]["interrupt"] = {"participant": "one", "when": "first_chunk", "text": "REVISED stop this request"}
        run = self.run_engine(validate(scenario))
        results = score(run, [{"step": 1, "participant": "one", "expected": "pass", "category": "silence"}, {"step": 1, "participant": "two", "expected": "speak", "category": "reply"}])
        self.assertEqual(results[0]["actual"], "cancelled")
        self.assertFalse(results[0]["matched"])
        self.assertEqual(run.data["turns"][1]["delivery"], "delivered")

    def test_staggered_resume_does_not_duplicate_already_delivered_turn(self):
        scenario = self.scenario()
        run = Run.create(self.home / "run", scenario, self.bindings())
        engine = Engine(run)
        original = engine.deliver
        calls = []

        def crash_after_receipt(turns, room):
            result = original(turns, room)
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("Simulated restart after atomic receipt")
            return result

        engine.deliver = crash_after_receipt
        with self.assertRaises(RuntimeError):
            asyncio.run(engine.execute())
        asyncio.run(Engine(run).execute())
        self.assertEqual(len(run.data["turns"]), 2)
        self.assertEqual(measures(run)["social"]["contributions"], 1)
        self.assertEqual(run.data["status"], "completed")

    def test_scripted_code_never_counts_as_real_work(self):
        scenario = self.scenario()
        scenario["steps"][0]["text"] = "```python\ndef imaginary():\n    return True\n```"
        run = self.run_engine(scenario)
        self.assertEqual(artifacts(run), [])

    def test_missing_and_unknown_are_missed_requests_not_silence(self):
        run = Run.create(self.home / "run", self.scenario(), self.bindings())
        run.data["turns"] = [{"id": "t", "step": 1, "participant": "one", "state": "unknown", "delivery": "uncertain"}]
        rows = score(run, [{"step": 1, "participant": "one", "expected": "pass", "category": "silence"}, {"step": 1, "participant": "two", "expected": "speak", "category": "request"}])
        self.assertEqual([row["actual"] for row in rows], ["unresolved", "not_observed"])
        self.assertFalse(any(row["matched"] for row in rows))

    def test_invalid_policy_and_silent_removed_opportunities_rejected(self):
        scenario = self.scenario()
        scenario["attention"]["ambient_threshold"] = "always_pass"
        with self.assertRaises(ValueError):
            validate(scenario)
        with self.assertRaises(ValueError):
            validate_expectations(self.scenario(), [{"step": 1, "participant": "one", "expected": "pass", "category": "silence"}])

    def prepared(self):
        write(self.home / "scenario.json", self.scenario())
        write(self.home / "bindings.json", self.bindings())
        case = {"id": "held", "split": "held_out", "scenario": "scenario.json", "expectations": [
            {"step": 1, "participant": "one", "expected": "speak", "category": "request"},
            {"step": 1, "participant": "two", "expected": "pass", "category": "covered"}]}
        write(self.home / "suite.json", {"schema": "agent-experiment-lab.attention-suite/1", "conditions": {"selective": {"policy": "selective", "scheduling": "staggered"}}, "cases": [case, {**case, "id": "calibration", "split": "calibration"}]})
        result = prepare(self.home / "suite.json", self.home / "bindings.json", self.home / "suite", load_scenario)
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["planned_opportunities"], 2)
        return self.home / "suite"

    def test_suite_freezes_both_splits_scores_actual_protocol_and_does_not_replay(self):
        output = self.prepared()
        frozen = read(output / "frozen-suite.json")
        self.assertEqual(len(frozen["cases"]), 2)
        result = asyncio.run(run_suite(output))
        totals = result["totals"]["selective"]
        self.assertEqual(totals["useful_passes"], 1)
        self.assertEqual(totals["required_responses_delivered"], 1)
        self.assertEqual(totals["actual_human_observations"], 0)
        requests_before = (self.home / "one/requests.jsonl").read_text()
        asyncio.run(run_suite(output))
        self.assertEqual((self.home / "one/requests.jsonl").read_text(), requests_before)
        run = Run(output / "held-selective-01")
        for turn in run.data["turns"]:
            prompt = read(run.path / turn["input"]["path"])["prompt"]
            self.assertNotIn('"expected"', prompt)
            self.assertNotIn('"category"', prompt)

    def test_suite_rejects_plan_tampering(self):
        output = self.prepared()
        plan = read(output / "plan.json")
        plan["runs"][0]["expectations"][0]["expected"] = "pass"
        write(output / "plan.json", plan)
        with self.assertRaises(ValueError):
            verified_plan(output)

    def test_repeat_order_counterbalances_without_changing_expected_participants(self):
        self.prepared()
        manifest = read(self.home / "suite.json")
        manifest["participant_order"] = "rotate"
        write(self.home / "suite.json", manifest)
        prepare(self.home / "suite.json", self.home / "bindings.json", self.home / "rotated", load_scenario, repetitions=2)
        first = read(self.home / "rotated/held-selective-01/scenario.json")
        second = read(self.home / "rotated/held-selective-02/scenario.json")
        self.assertEqual(first["steps"][1]["participants"], ["one", "two"])
        self.assertEqual(second["steps"][1]["participants"], ["two", "one"])
        plan = verified_plan(self.home / "rotated")
        self.assertEqual(plan["runs"][0]["expectations"], plan["runs"][1]["expectations"])

    def test_shipped_suite_has_complete_oracles_and_separate_calibration(self):
        manifest = read(ROOT / "examples/attention/suite.json")
        self.assertEqual({case["split"] for case in manifest["cases"]}, {"calibration", "held_out"})
        for case in manifest["cases"]:
            scenario = load_scenario(ROOT / "examples/attention" / case["scenario"])
            validate_expectations(scenario, case["expectations"])

    def test_handoff_evaluator_checks_exact_contents_and_rejects_execution(self):
        code = 'def handoff_state(owner, accepted, blocked):\n    if owner is None:\n        return "unassigned"\n    if not accepted:\n        return "offered"\n    if blocked:\n        return "blocked"\n    return "active"\n'
        result = subprocess.run([sys.executable, str(ROOT / "examples/evaluate_handoff.py")], input=json.dumps({"content": code}), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(json.loads(result.stdout)["checks"]), 12)
        result = subprocess.run([sys.executable, str(ROOT / "examples/evaluate_handoff.py")], input=json.dumps({"content": "import os\nos.system('exit 0')"}), capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
