import hashlib
import io
import json
import copy
import http.client
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from fixtures import ScriptedProvider, WorkshopMCP, tool_failed
from oracles import artifact_oracle, recovered_job_oracle, source_identity_oracle


class ReferenceTests(unittest.TestCase):
    def test_error_status_is_preserved_not_guessed_from_content(self):
        refused = {"content": [{"type": "text", "text": "Not available"}], "isError": True}
        self.assertIs(tool_failed(json.dumps(refused)), True)
        self.assertIs(tool_failed({"success": False, "output": "Not available"}), True)
        # A broken wrapper must not pass our refusal oracle just because the
        # output sounds like a failure. This is an observable integration defect.
        self.assertIs(tool_failed({"success": True, "output": "Not available"}), False)
        self.assertIsNone(tool_failed("Not available"))

    def test_lost_build_reply_is_followed_by_lookup_not_another_submission(self):
        calls = []
        def api(method, path, body=None):
            calls.append((method, path, body))
            if method == "POST":
                return {"id": "job"}
            return {"outcome": "recorded", "job": {"id": "job", "status": "interrupted"}}
        def lose_reply(body):
            api("POST", "/api/v1/projects/project/builds", body)
            raise http.client.RemoteDisconnected("The accepted reply was lost")
        adapter = WorkshopMCP(api, {"id": "project", "revision": 3}, submit=lose_reply)
        call = lambda name: {"id": 1, "method": "tools/call", "params": {"name": name, "arguments": {"request_id": "creation"}}}
        lost = adapter.dispatch(call("profile_build"))["result"]
        self.assertIs(lost["isError"], True)
        self.assertEqual(lost["structuredContent"]["acceptance"], "unknown")
        found = adapter.dispatch(call("profile_inspect"))["result"]["structuredContent"]
        self.assertEqual(found["job"]["status"], "interrupted")
        self.assertEqual([c[0] for c in calls], ["POST", "GET"])
        self.assertEqual(calls[0][2], {"expected_revision": 3, "request_id": "creation"})

    def test_unknown_lookup_has_no_mutating_fallback(self):
        calls = []
        def api(method, path, body=None):
            calls.append(method)
            return {"outcome": "unknown", "job": None}
        adapter = WorkshopMCP(api, {"id": "project", "revision": 1})
        result = adapter.dispatch({"id": 1, "method": "tools/call", "params": {
            "name": "profile_inspect", "arguments": {"request_id": "unknown"}}})
        self.assertEqual(result["result"]["structuredContent"]["outcome"], "unknown")
        self.assertEqual(calls, ["GET"])

    def test_provider_requires_actual_exposed_tool_and_original_source_handle(self):
        provider = ScriptedProvider(io.StringIO())
        provider.set_plan([("create", "work_create", lambda p: {"source_input_id": p.source_input})])
        response = provider.dispatch({"messages": [{"role": "user", "content":
            '[Original input reference]\nsource_input_id: "the-original-input"\n[/Original input reference]'}],
            "tools": [{"function": {"name": "mcp_1_work_create"}}]})
        self.assertIn(b"the-original-input", response)
        self.assertEqual(provider.events[0]["arguments"]["source_input_id"], "the-original-input")
        other = ScriptedProvider(io.StringIO())
        other.set_plan([("create", "work_create", {})])
        self.assertEqual(other.dispatch({"messages": [], "tools": []})[0], 500)
        self.assertIn("Actual engine did not expose", other.failure)

    def test_provider_does_not_reuse_an_unrelated_tool_result(self):
        provider = ScriptedProvider(io.StringIO())
        provider.set_plan([("read", "work_get", {"id": "work"}), "Done"])
        provider.dispatch({"messages": [], "tools": [{"function": {"name": "mcp_1_work_get"}}]})
        self.assertEqual(provider.dispatch({"messages": [{"role": "tool", "tool_call_id": "an-earlier-call",
            "content": '{"id":"work","isError":false}'}]})[0], 500)
        self.assertIn("Missing actual result", provider.failure)
        provider.dispatch({"messages": [{"role": "tool", "tool_call_id": provider.active_call_id,
            "content": '{"structuredContent":{"id":"work"},"isError":false}'}]})
        self.assertEqual(provider.results["read"], {"id": "work"})
        self.assertIs(provider.events[-1]["failed"], False)

    def test_background_utility_does_not_consume_foreground_decisions(self):
        provider = ScriptedProvider(io.StringIO())
        provider.set_plan(["The real foreground result"])
        reply = provider.dispatch({"messages": [{"role": "user", "content": "Utility input"}],
            "tools": [], "metadata": {"stream": False}, "max_output_tokens": 256})
        self.assertIn(b"defer", reply)
        self.assertFalse(provider.finished.is_set())
        self.assertEqual(provider.plan, ["The real foreground result"])
        self.assertEqual(provider.events[-1]["utility_request"], "bounded_nonstreaming")

    def test_artifact_oracle_rejects_claims_without_matching_saved_contents(self):
        class Tool:
            def __init__(self):
                self.files = {"communication.md": "Concise, concrete language.", "working-style.md": "Compare evidence.",
                              "claims.json": "[]", "evaluation-summary.json": "{}"}
                self.hashes = {k: hashlib.sha256(v.encode()).hexdigest() for k, v in self.files.items()}
            def api(self, method, path):
                manifest = {"files": self.hashes, "subject_key": "project",
                    "revision": "revision", "required_context": ["communication.md", "working-style.md"]}
                return {"files": {**self.files, "manifest.json": json.dumps(manifest)}, "manifest": manifest}
        tool = Tool()
        artifact_oracle(tool, "project", "revision")
        tool.files["communication.md"] = "A confident claim of success."
        with self.assertRaises(AssertionError):
            artifact_oracle(tool, "project", "revision")
        tool.files["communication.md"] = "Concise, concrete language, changed after hashing."
        with self.assertRaises(AssertionError):
            artifact_oracle(tool, "project", "revision")
        for missing in (None, "communication.md", "claims.json"):
            tool = Tool()
            if missing is None:
                tool.hashes = {}
            else:
                del tool.hashes[missing]
            with self.assertRaises(AssertionError):
                artifact_oracle(tool, "project", "revision")

    def test_recovery_oracle_rejects_another_complete_job_or_missing_loss(self):
        events = [{"operation": "build", "request_id": "request", "job_id": "accepted", "reply": "deliberately_lost"}]
        recovered = {"outcome": "recorded", "job": {"status": "complete", "id": "accepted", "project_id": "project",
                    "kind": "build", "submission": {"request_id": "request"}}}
        recovered_job_oracle(events, recovered, "project", "request")
        for field, value in (("id", "another-complete-job"), ("project_id", "another-project"),
                             ("submission", {"request_id": "another-request"})):
            wrong = copy.deepcopy(recovered)
            wrong["job"][field] = value
            with self.assertRaises(AssertionError):
                recovered_job_oracle(events, wrong, "project", "request")
        with self.assertRaises(AssertionError):
            recovered_job_oracle([{**events[0], "reply": "delivered"}], recovered, "project", "request")

    def test_source_chain_rejects_wrong_original_identity_or_revision(self):
        sources = [{"id": "request", "revision": "original-revision", "occurredAt": 123}]
        room = {"id": "room", "messages": [{"id": "request", "role": "user", "text": "Please draft this."}]}
        work = {"id": "work", "source": {"conversation_id": "room", "message_id": "request"},
                "source_input": {"inputId": "input", "sessionId": "session", "sources": sources}}
        receipt = {"sourceId": "request", "revision": "original-revision", "occurredAt": 123, "inputId": "input",
                   "work": [{"id": "work", "inputId": "input"}]}
        source = {"request_id": "request", "publication": {"state": "saved", "message_id": "request",
            "conversation_id": "room", "source_sequence": 1, "created_at": 123}, "items": [{"id": "input",
            "agent_id": "default", "message_id": "request", "session_id": "session", "source_sequence": 1,
            "source_delivery": {"input_id": "input", "sources": sources, "receipt": {"receipts": [receipt]}}}]}
        source_identity_oracle(source, room, "request", work, "Please draft this.")
        for field, value in (("sourceId", "another-request"), ("revision", "another-revision"), ("inputId", "another-input")):
            changed = copy.deepcopy(source)
            changed["items"][0]["source_delivery"]["receipt"]["receipts"][0][field] = value
            with self.assertRaises(AssertionError):
                source_identity_oracle(changed, room, "request", work)
        changed = copy.deepcopy(work)
        changed["source_input"]["sources"][0]["revision"] = "another-revision"
        with self.assertRaises(AssertionError):
            source_identity_oracle(source, room, "request", changed)
        with self.assertRaises(AssertionError):
            source_identity_oracle(source, room, "request", work, "A different user request.")


if __name__ == "__main__":
    unittest.main()
