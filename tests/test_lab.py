import asyncio
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from experiment_lab.analysis import artifacts, compare, evaluate, measures, report
from experiment_lab.batch import batch
from experiment_lab.cli import load_scenario
from experiment_lab.engine import Engine, decision, projection, resolve
from experiment_lab.imports import import_slack
from experiment_lab.network import api, public_transcript, submit
from experiment_lab.scenario import validate, validate_bindings
from experiment_lab.storage import Run, digest, read, write

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/acp_agent.py"


class LabTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="agent-lab-test-")
        self.home = Path(self.temporary.name)
        self.serial = 0

    def tearDown(self):
        self.temporary.cleanup()

    def scenario(self, steps=None, members=None):
        return validate({"schema": "agent-experiment-lab.scenario/1", "label": "Protocol fixture experiment",
                         "participants": {key: {"label": key, "kind": "protocol_fixture"} for key in ("one", "two")},
                         "rooms": {"room": {"members": members if members is not None else ["one", "two"]}, "private": {"members": ["one"]}},
                         "steps": steps or [{"action": "cue", "room": "room", "text": "Discuss."}, {"action": "round", "room": "room"}],
                         "limits": {"turn_seconds": 2}})

    def new(self, scenario=None, modes=None):
        self.serial += 1
        scenario = scenario or self.scenario()
        modes = modes or {}
        bindings = {"schema": "agent-experiment-lab.bindings/1", "participants": {
            key: {"command": [sys.executable, str(FIXTURE), "--home", str(self.home / f"endpoint-{self.serial}-{key}"), "--mode", modes.get(key, "normal")], "cwd": str(self.home)}
            for key in scenario["participants"]}}
        return Run.create(self.home / f"run-{self.serial}", scenario, bindings)

    def run_engine(self, run, steps=None):
        with run.lock():
            asyncio.run(Engine(run).execute(steps))
        return Run(run.path)

    def test_fleet_transcript_is_opt_in_and_projects_only_delivered_messages(self):
        run = self.new()
        run.data["messages"] = [{"id":"one", "speaker":"one", "kind":"protocol_fixture", "room":"room", "text":"Delivered **result**", "private_draft":"DO NOT UPLOAD", "grant":"DO NOT UPLOAD"}]
        run.data["turns"] = [{"prompt":"DO NOT UPLOAD", "response":"Unpublished"}]
        self.assertNotIn("DO NOT UPLOAD", json.dumps(public_transcript(run)))
        summary = {"measurements": {"independent_checks":9}}
        with patch("experiment_lab.network.api", return_value={"id":"report", "revision":1}) as network:
            submit(run, summary, "https://fleet.example", "unused")
            self.assertEqual(network.call_count, 1)
        with patch("experiment_lab.network.api", side_effect=[{"id":"report", "revision":1}, {"id":"report", "revision":2, "message_count":1}]) as network:
            receipt = submit(run, summary, "https://fleet.example", "unused", include_transcript=True)
            self.assertEqual(network.call_args_list[1].args[2], "/api/v1/experiments/report/transcript")
            self.assertEqual(network.call_args_list[1].kwargs["method"], "PUT")
            self.assertEqual(receipt["transcript"]["message_count"], 1)
            payload = network.call_args_list[1].args[3]
            self.assertEqual(payload["messages"][0]["kind"], "protocol_fixture")
            self.assertNotIn("DO NOT UPLOAD", json.dumps(payload))

    def test_unknown_or_oversized_transcripts_fail_before_creating_a_fleet_report(self):
        run = self.new()
        for kind, text in [("private_draft", "secret"), ("support_agent", "x" * 128_001)]:
            run.data["messages"] = [{"id":"one", "speaker":"one", "kind":kind, "room":"room", "text":text}]
            with patch("experiment_lab.network.api") as network:
                with self.assertRaises(ValueError):
                    submit(run, {"measurements":{}}, "https://fleet.example", "unused", include_transcript=True)
                network.assert_not_called()

    def test_parallel_participants_get_same_visible_baseline_and_private_drafts(self):
        run = self.run_engine(self.new())
        self.assertEqual(run.data["status"], "completed")
        self.assertEqual(len(run.data["turns"]), 2)
        self.assertEqual(len(run.data["messages"]), 3)
        histories = []
        for turn in run.data["turns"]:
            prompt = read(run.path / turn["input"]["path"])["prompt"]
            histories.append(json.loads(prompt.split("\n\n", 1)[1])["history"])
        self.assertEqual(histories[0], histories[1])
        self.assertEqual(len(histories[0]), 1)
        self.assertEqual(measures(run)["social"]["human_feedback_count"], 0)

    def test_interrupted_draft_stays_private_and_next_turn_knows_delivery(self):
        scenario = self.scenario([
            {"action": "cue", "room": "room", "text": "INTERRUPT this draft"},
            {"action": "round", "room": "room", "participants": ["one"], "interrupt": {"when": "first_chunk", "participant": "one", "text": "REVISED acceptance; reopen work"}},
            {"action": "round", "room": "room", "participants": ["one"]},
        ])
        run = self.run_engine(self.new(scenario))
        self.assertEqual(run.data["turns"][0]["delivery"], "not_delivered")
        self.assertEqual(run.data["turns"][0]["stop_reason"], "cancelled")
        self.assertEqual(run.data["turns"][1]["delivery"], "delivered")
        self.assertIn("present: True", run.data["messages"][-1]["text"])
        self.assertNotIn("STALE PRIVATE DRAFT", json.dumps(run.data["messages"]))
        self.assertEqual(measures(run)["technical"]["cancellations_confirmed"], 1)

    def test_unacknowledged_cancellation_is_unknown_and_not_replayed(self):
        scenario = self.scenario([
            {"action": "cue", "room": "room", "text": "INTERRUPT"},
            {"action": "round", "room": "room", "participants": ["one"], "interrupt": {"when": "first_chunk", "participant": "one", "text": "REVISED"}},
        ])
        run = self.run_engine(self.new(scenario, {"one": "ignore_cancel"}))
        self.assertEqual(run.data["status"], "needs_resolution")
        self.assertEqual(run.data["turns"][0]["delivery"], "uncertain")
        events = len(run.data["events"])
        run = self.run_engine(run)
        self.assertEqual(len(run.data["events"]), events)
        self.assertEqual(measures(run)["technical"]["cancellations_confirmed"], 0)

    def test_intervention_withholds_other_concurrent_stale_drafts(self):
        scenario = self.scenario([
            {"action": "cue", "room": "room", "text": "INTERRUPT"},
            {"action": "round", "room": "room", "interrupt": {"when": "first_chunk", "participant": "one", "text": "REVISED acceptance"}},
        ])
        run = self.run_engine(self.new(scenario, {"two": "quick"}))
        self.assertEqual(run.data["status"], "completed")
        self.assertEqual([turn["delivery"] for turn in run.data["turns"]], ["not_delivered", "not_delivered"])
        self.assertEqual(len(run.data["messages"]), 2)

    def test_total_deadline_during_turn_records_ambiguous_execution(self):
        scenario = self.scenario([
            {"action": "cue", "room": "room", "text": "INTERRUPT"},
            {"action": "round", "room": "room", "participants": ["one"], "interrupt": {"when": "first_chunk", "participant": "one", "text": "REVISED"}},
        ])
        scenario["limits"].update(max_seconds=1, turn_seconds=20)
        run = self.run_engine(self.new(scenario, {"one": "ignore_cancel"}))
        self.assertEqual(run.data["status"], "needs_resolution")
        self.assertEqual(run.data["stop_reason"], "time_limit_during_turn")
        self.assertEqual(run.data["turns"][0]["state"], "unknown")

    def test_resume_loads_existing_sessions_without_replaying_messages(self):
        scenario = self.scenario([
            {"action": "cue", "room": "room", "text": "First"},
            {"action": "round", "room": "room"},
            {"action": "cue", "room": "room", "text": "Second"},
            {"action": "round", "room": "room"},
        ])
        run = self.run_engine(self.new(scenario), 2)
        sessions = copy.deepcopy(run.data["sessions"])
        self.assertEqual(run.data["status"], "paused")
        run = self.run_engine(run)
        self.assertEqual(run.data["sessions"], sessions)
        self.assertEqual(measures(run)["technical"]["sessions_loaded"], 2)
        self.assertEqual(measures(run)["social"]["contributions"], 4)
        self.assertNotIn("replayed historical", json.dumps(run.data["messages"]))

    def test_no_load_capability_recreates_context_honestly(self):
        scenario = self.scenario([
            {"action": "cue", "room": "room", "text": "First"},
            {"action": "round", "room": "room", "participants": ["one"]},
            {"action": "round", "room": "room", "participants": ["one"]},
        ])
        run = self.run_engine(self.new(scenario, {"one": "no_load"}), 2)
        previous = dict(run.data["sessions"])
        run = self.run_engine(run)
        self.assertNotEqual(run.data["sessions"], previous)
        self.assertEqual(measures(run)["technical"]["sessions_recreated"], 1)
        context = json.loads(read(run.path / run.data["turns"][-1]["input"]["path"])["prompt"].split("\n\n", 1)[1])
        self.assertEqual(len(context["history"]), 2)
        self.assertEqual(context["response_delivery"]["items"][0]["delivery"], "delivered")

    def test_published_checkpoint_is_not_republished_after_crash_before_cursor(self):
        run = self.run_engine(self.new())
        run.data.update(cursor=1, status="running")
        before = copy.deepcopy(run.data["messages"])
        run.save()
        run = self.run_engine(run)
        self.assertEqual(run.data["messages"], before)
        self.assertEqual(len(run.data["turns"]), 2)

    def test_room_separation_and_late_join(self):
        scenario = self.scenario([
            {"action": "cue", "room": "private", "text": "PRIVATE PROJECT SECRET"},
            {"action": "round", "room": "private"},
            {"action": "cue", "room": "room", "text": "PUBLIC BRIEF"},
            {"action": "round", "room": "room"},
            {"action": "join", "room": "room", "participant": "two"},
            {"action": "round", "room": "room"},
        ], members=["one"])
        run = self.run_engine(self.new(scenario))
        for turn in run.data["turns"]:
            prompt = read(run.path / turn["input"]["path"])["prompt"]
            if turn["room"] == "room":
                self.assertNotIn("PRIVATE PROJECT SECRET", prompt)
                self.assertIn("PUBLIC BRIEF", prompt)
        late = next(turn for turn in run.data["turns"] if turn["participant"] == "two")
        self.assertIn("Contribution from one", read(run.path / late["input"]["path"])["prompt"])
        self.assertNotEqual(run.data["sessions"]["one:room"], run.data["sessions"]["one:private"])

    def test_drop_after_prompt_requires_explicit_resolution(self):
        run = self.run_engine(self.new(modes={"one": "disconnect"}))
        self.assertEqual(run.data["status"], "needs_resolution")
        failed = next(turn for turn in run.data["turns"] if turn["state"] == "unknown")
        initial_count = len(run.data["turns"])
        with run.lock():
            resolve(run, failed["id"], "Inspected isolated fixture process; it exited. Skip without rerunning.")
        run = self.run_engine(run)
        self.assertEqual(run.data["status"], "completed")
        self.assertEqual(len(run.data["turns"]), initial_count)
        self.assertEqual(len([message for message in run.data["messages"] if message["speaker"] == "one"]), 0)

    def test_crash_checkpoint_not_resent(self):
        run = self.new()
        run.data["turns"].append({"id": "stopped-turn", "participant": "one", "room": "room", "step": 1, "state": "in_flight", "delivery": "pending"})
        run.save()
        run = self.run_engine(run)
        self.assertEqual(run.data["status"], "needs_resolution")
        self.assertEqual(run.data["turns"][0]["state"], "unknown")
        self.assertEqual(run.data["sessions"], {})

    def test_foreign_session_output_not_published(self):
        run = self.run_engine(self.new(modes={"one": "foreign_session"}))
        self.assertEqual(run.data["status"], "needs_resolution")
        self.assertNotIn("leak", json.dumps(run.data["messages"]))

    def test_unoffered_permissions_cancelled_and_counted(self):
        run = self.run_engine(self.new(modes={"one": "permission"}))
        self.assertEqual(run.data["status"], "completed")
        metrics = measures(run)["technical"]
        self.assertEqual(metrics["permission_requests_cancelled"], 1)
        self.assertEqual(metrics["tool_updates"], 1)

    def test_plain_reply_and_voluntary_pass(self):
        run = self.run_engine(self.new(modes={"one": "plain", "two": "pass"}))
        self.assertEqual(measures(run)["social"]["voluntary_passes"], 1)
        self.assertEqual(measures(run)["social"]["contributions"], 1)

    def test_malformed_envelope_stays_private(self):
        run = self.run_engine(self.new(modes={"one": "malformed"}))
        one = next(turn for turn in run.data["turns"] if turn["participant"] == "one")
        self.assertEqual(one["delivery"], "not_delivered")
        self.assertNotIn("badly formed", json.dumps(run.data["messages"]))

    def test_progress_before_final_envelope_stays_private(self):
        run = self.run_engine(self.new(modes={"one": "progress"}))
        one = next(turn for turn in run.data["turns"] if turn["participant"] == "one")
        self.assertEqual(one["decision"]["format"], "json_with_progress")
        self.assertNotIn("Private progress", json.dumps(run.data["messages"]))
        self.assertIn("Private progress", read(run.path / one["output"]["path"])["text"])
        self.assertEqual(measures(run)["technical"]["final_envelope_formats"]["json_with_progress"], 1)

    def test_final_envelope_with_progress_requires_complete_terminal_json(self):
        self.assertEqual(decision('Working.\n{"action":"pass","reason":"No new point"}')["action"], "pass")
        self.assertEqual(decision('Working.\n```json\n{"action":"speak","text":"Ready"}\n```')["text"], "Ready")
        self.assertEqual(decision('Working.\n{"action":"speak","text":"unfinished')["action"], "invalid")
        self.assertEqual(decision('Working.\n{"action":"speak","text":"Maybe"}\nMore trailing prose')["action"], "invalid")

    def test_turn_limit_stops_before_additional_model_work(self):
        scenario = self.scenario()
        scenario["limits"]["max_turns"] = 1
        run = self.run_engine(self.new(scenario))
        self.assertEqual(run.data["status"], "limited")
        self.assertEqual(len(run.data["turns"]), 0)

    def test_exact_artifact_separate_evaluator_and_report_escaping(self):
        scenario = self.scenario([{ "action": "cue", "room": "room", "text": "ARTIFACT <script>alert(1)</script>"}, {"action": "round", "room": "room", "participants": ["one"]}])
        scenario["evaluators"] = [{"id": "status", "room": "room", "language": "python", "command": [sys.executable, str(ROOT / "examples/evaluate_status.py")]}]
        run = self.run_engine(self.new(scenario))
        artifact = artifacts(run)[0]
        receipt = evaluate(run, "status")
        self.assertTrue(receipt["passed"])
        self.assertEqual(len(receipt["checks"]), 9)
        self.assertEqual(receipt["artifact_sha256"], artifact["sha256"])
        self.assertEqual(receipt["source"], "separate_operator_process")
        self.assertEqual(measures(run)["task"]["completion"], "not_inferred_from_conversation")
        report(run)
        page = (run.path / "report.html").read_text()
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;", page)

    def test_evaluator_rejects_artifact_imports(self):
        evaluator = ROOT / "examples/evaluate_status.py"
        result = subprocess.run([sys.executable, str(evaluator)], input=json.dumps({"content": "import os\ndef profile_status(a,b,c):\n return 'current'\n"}), capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["checks"][0]["passed"])

    def test_evaluation_keeps_frozen_scenario_and_rejects_changing_verifier(self):
        scenario = self.scenario([{"action":"cue","room":"room","text":"ARTIFACT"}, {"action":"round","room":"room","participants":["one"]}])
        scenario["evaluators"] = [{"id":"status","room":"room","language":"python","command":[sys.executable,str(ROOT / "examples/evaluate_status.py")]}]
        run = self.run_engine(self.new(scenario))
        original = read(run.path / "scenario.json")
        changed = dict(original, label="Changed acceptance condition")
        write(run.path / "scenario.json", changed)
        with self.assertRaisesRegex(ValueError,"Scenario changed"):
            evaluate(run,"status")
        self.assertEqual(run.data["evaluations"],[])
        write(run.path / "scenario.json", original)
        receipt = evaluate(run,"status")
        self.assertTrue(receipt["passed"])
        self.assertEqual(receipt["scenario_sha256"],run.data["scenario_sha256"])
        verifier = run.path.parent / "changing-verifier.py"
        verifier.write_text("import json, pathlib, sys\nx=json.load(sys.stdin)\np=pathlib.Path(__file__)\np.write_text(p.read_text()+'\\n# changed\\n')\nprint(json.dumps({'artifact_sha256':x['artifact']['sha256'],'checks':[{'name':'claimed','passed':True}]}))\n")
        scenario["evaluators"][0]["command"] = [sys.executable,str(verifier)]
        altered = self.run_engine(self.new(scenario))
        receipt = evaluate(altered,"status")
        self.assertEqual(receipt["status"],"error")
        self.assertFalse(receipt["passed"])

    def test_report_links_recorded_observations_without_trusting_external_paths(self):
        run = self.run_engine(self.new())
        reference = run.evidence('profile-use.json', {'status': 'supplied_current', 'behavior_quality': 'not_evaluated'})
        run.data['observations'] = [{'participant': 'one', 'resource': '/api/v1/profile-use', 'evidence': reference, 'classification': 'reported_by_management_api'}, {'evidence': {'path': 'https://untrusted.example/token'}}]
        value = report(run)
        self.assertEqual(len(value['observations']), 2)
        page = (run.path / 'report.html').read_text()
        self.assertIn('href="evidence/profile-use.json"', page)
        self.assertNotIn('href="https://untrusted', page)
        self.assertIn('do not establish behavioral quality', page)

    def test_evaluator_checks_selected_author_not_later_peer_copy(self):
        scenario = self.scenario([{ "action": "cue", "room": "room", "text": "ARTIFACT"}, {"action": "round", "room": "room"}])
        scenario["evaluators"] = [{"id": "status", "room": "room", "language": "python", "participant": "one", "command": [sys.executable, str(ROOT / "examples/evaluate_status.py")]}]
        run = self.run_engine(self.new(scenario))
        receipt = evaluate(run, "status")
        self.assertTrue(receipt["passed"])
        self.assertEqual(receipt["artifact_speaker"], "one")
        run.data["messages"] = [message for message in run.data["messages"] if message["speaker"] != "one"]
        with self.assertRaises(ValueError):
            evaluate(run, "status")

    def test_lock_blocks_duplicate_runner(self):
        run = self.new()
        with run.lock():
            with self.assertRaises(ValueError):
                with Run(run.path).lock():
                    self.fail("acquired duplicate lock")

    def test_changed_configuration_cannot_resume_as_same_experiment(self):
        run = self.new()
        scenario = read(run.path / "scenario.json")
        scenario["label"] = "Different condition"
        write(run.path / "scenario.json", scenario)
        with self.assertRaises(ValueError):
            Engine(run)

    def test_comparison_marks_different_scenarios_and_no_human_feedback(self):
        first = self.run_engine(self.new())
        other = self.scenario()
        other["label"] = "Different scenario"
        second = self.run_engine(self.new(other))
        result = compare([first, second], self.home / "comparison")
        self.assertFalse(result["comparability"]["same_scenario"])
        self.assertFalse(result["comparability"]["causal_effect_established"])
        self.assertEqual(result["runs"][0]["measurements"]["social"]["human_feedback_count"], 0)

    def test_history_truncation_preserves_truth_about_coverage(self):
        run = self.new()
        run.data["messages"] = [{"id": "one", "seq": 1, "room": "room", "text": "x" * 500, "kind": "operator_cue"}, {"id": "two", "seq": 2, "room": "room", "text": "latest", "kind": "operator_cue"}]
        scenario = self.scenario()
        scenario["limits"]["history_characters"] = 100
        result = projection(run, scenario, "room", "one")
        self.assertTrue(result["history_truncated"])
        self.assertEqual(len(result["history"]), 1)

    def test_api_requires_https_origin_before_reading_credentials(self):
        for origin in ("http://localhost", "https://user:pass@host", "https://host/path", "https://host?x=y"):
            with self.assertRaises(ValueError):
                api(origin, "/nonexistent", "/api/v1/status")

    def test_unsafe_or_invalid_scenarios_rejected(self):
        scenario = self.scenario()
        scenario["steps"] = [{"action": "round", "room": "room", "participants": ["stranger"]}]
        with self.assertRaises(ValueError):
            validate(scenario)
        scenario = self.scenario()
        scenario["participants"]["one"]["kind"] = "human"
        with self.assertRaises(ValueError):
            validate(scenario)

    def test_example_validates_and_evaluator_paths_are_explicit(self):
        scenario = load_scenario(ROOT / "examples/workshop.json")
        self.assertEqual(len(scenario["participants"]), 5)
        self.assertTrue(Path(scenario["evaluators"][0]["command"][1]).is_absolute())

    def test_import_slack_preserves_sources_without_prompts_or_human_scores(self):
        source = self.home / "slack"
        source.mkdir()
        write(source / "run.json", {"schema": "persona-workshop.slack-trial/1", "id": "fixture-slack",
                                   "rooms": [{"key": "room", "roster": ["alex-sim", "builder"]}]})
        write(source / "rooms/room.json", {"messages": [{"ts": "1.2", "role": "alex-sim", "name": "Alex simulation", "text": "I approve this.", "url": "https://example.test/message/1", "operator_cue": False}]})
        run = import_slack(source, self.home / "imported")
        self.assertEqual(run.data["experience"], "slack_recording")
        self.assertEqual(run.data["messages"][0]["kind"], "simulated_human")
        self.assertEqual(run.data["messages"][0]["url"], "https://example.test/message/1")
        self.assertEqual(run.data["turns"], [])
        self.assertEqual(measures(run)["social"]["human_feedback_count"], 0)
        self.assertIsNone(measures(run)["technical"]["cancellations_requested"])

    def test_batch_creates_separate_runs_and_descriptive_comparison(self):
        template = self.new()
        manifest = self.home / "batch.json"
        write(manifest, {"schema": "agent-experiment-lab.batch/1", "max_parallel": 2,
                         "cases": [{"id": "condition", "scenario": str(template.path / "scenario.json"),
                                    "bindings": str(template.path / "bindings.json"), "repetitions": 2}]})
        result = asyncio.run(batch(manifest, self.home / "batch-output", load_scenario))
        self.assertEqual(len(result["runs"]), 2)
        self.assertTrue(all(item["status"] == "completed" for item in result["runs"]))
        self.assertTrue(result["comparability"]["same_bindings"])
        self.assertFalse(result["comparability"]["causal_effect_established"])
        self.assertNotEqual(result["runs"][0]["run_id"], result["runs"][1]["run_id"])


if __name__ == "__main__":
    unittest.main()
