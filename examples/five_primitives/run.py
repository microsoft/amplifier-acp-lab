#!/usr/bin/env python3
"""A disposable five-primitives journey through real public component APIs."""
import argparse
import getpass
import hashlib
import html
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiment_lab.platform import private_directory, ProcessJob
from fixtures import LocalServer, ScriptedProvider, WorkshopMCP, tool_failed
from oracles import artifact_oracle, recovered_job_oracle, source_identity_oracle


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Installation:
    def __init__(self, name, binary, output, env):
        self.name, self.binary = name, str(binary.absolute())
        self.home = output / name
        self.env, self.process, self.job = env, None, None
        self.log = (output / (name + ".log")).open("w")
        self.sequence = 0

    def cli(self, *args, raw=False):
        p = subprocess.run([self.binary, "--home", str(self.home), *map(str, args)],
                           env=self.env, capture_output=True, text=True, timeout=35)
        if p.returncode:
            raise RuntimeError(f"{self.name} command failed: {p.stderr.strip()}")
        return p.stdout if raw else json.loads(p.stdout)

    def api(self, method, path, body=None):
        args = ["api", method, path]
        if body is not None:
            self.sequence += 1
            # Private command inputs can contain disposable credentials.
            target = self.home / f"reference-request-{self.sequence}.json"
            save(target, body)
            args += ["--file" if self.name == "instance" else "--body-file", target]
        return self.cli(*args)

    def start(self, command=None, ready_file=None, timeout=15):
        self.process = subprocess.Popen(command or [self.binary, "--home", str(self.home), "serve"],
            env=self.env, stdout=self.log, stderr=self.log,
            start_new_session=os.name != "nt",
            creationflags=0x4 if os.name == "nt" else 0)
        self.job = ProcessJob(self.process.pid)
        self.job.resume()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"{self.name} exited; see {self.log.name}")
            if (self.home / (ready_file or ("endpoints.json" if self.name == "instance" else "runtime.json"))).exists():
                return
            time.sleep(.05)
        raise TimeoutError(f"{self.name} did not become ready")

    def close(self):
        if self.process and self.process.poll() is None:
            if os.name == "nt":
                self.job.close()
            else:
                os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(5)
        if self.job:
            self.job.close()
        self.log.close()


def approve_fixture_permissions(conversations, room, provider, seen):
    for permission in room.get("permissions", []):
        if permission["id"] in seen:
            continue
        # The deterministic provider can ask for only these explicitly scripted
        # operations in the newly created installations. Never grant remembered
        # permissions or terminal/filesystem operations.
        pending = next((e for e in reversed(provider.events) if "tool" in e), {})
        assert pending.get("tool") in {"work_create", "work_command", "work_get", "profile_build", "profile_inspect"}, permission
        raw_input = permission["tool_call"]["rawInput"]
        assert raw_input.get("tool") == pending["tool"] and raw_input.get("arguments") == pending["arguments"], permission
        options = permission.get("options", [])
        selected = next(o for o in options if o.get("kind") == "allow_once")
        option_id = selected.get("optionId", selected.get("option_id"))
        conversations.api("POST", f"/api/v1/conversations/{room['id']}/permissions/{permission['id']}",
                          {"option_id": option_id})
        seen.add(permission["id"])


def wait_turn(conversations, room_id, provider, timeout=180, expect_failure=False):
    deadline, seen = time.monotonic() + timeout, set()
    while time.monotonic() < deadline:
        assert provider.failure is None, provider.failure
        room = conversations.api("GET", f"/api/v1/conversations/{room_id}")
        approve_fixture_permissions(conversations, room, provider, seen)
        rows = room.get("deliveries", [])
        if isinstance(rows, dict):
            rows = rows.get("items", [])
        if provider.finished.is_set() and room.get("status") == "idle":
            return room
        failures = [r for r in rows if r.get("state") in {"failed", "unknown", "notAccepted"}]
        if failures and room.get("status") in {"idle", "error", "interrupted"}:
            if expect_failure:
                return room
            raise AssertionError({"delivery_failure": failures, "room": room})
        time.sleep(.1)
    raise TimeoutError(f"Reference turn did not settle: {room}")


def command(previous, change):
    def args(p):
        work = p.results[previous]
        assert isinstance(work, dict) and work.get("id") and work.get("revision"), work
        return {"id": work["id"], "expected_revision": work["revision"], "command": change(p) if callable(change) else change}
    return args


def main(args):
    output = args.output.resolve()
    private_directory(output, exist_ok=False)
    workspace = output / "workspace"
    private_directory(workspace)
    # Inherit no production home, model credential, service URL or provider key.
    env = {k: os.environ[k] for k in ("PATH", "USER", "LANG", "SYSTEMROOT", "WINDIR", "TEMP", "TMP") if k in os.environ}
    env["HOME"] = str(output / "process-home")
    private_directory(Path(env["HOME"]))
    services, servers = [], []
    checks = []
    report = {"kind": "deterministic_component_composition", "actual_model_coverage": False,
        "engine": "unified" if args.unified_python else "native",
        "production_operations": 0, "companion_activation": False, "checks": checks,
        "binaries": {n: {"path": str(getattr(args, n).resolve()), "sha256": digest(getattr(args, n))}
                     for n in ("instance", "runtime", "conversations", "workshop")}}
    report["fixture_sources"] = {str(path.relative_to(Path(__file__).parent)): digest(path)
                                 for path in sorted(Path(__file__).parent.rglob("*.py"))}
    report["extractor_fixture"] = {"path": str(args.extractor_fixture.resolve()), "sha256": digest(args.extractor_fixture)}
    save(output / "provenance.json", report)
    trace = (output / "provider-inputs.jsonl").open("w")
    provider = ScriptedProvider(trace)
    model_server = LocalServer(provider.dispatch)
    servers.append(model_server)
    try:
        runtime_home = output / "runtime"
        subprocess.run([str(args.runtime.resolve()), "--home", str(runtime_home), "init", "--workspace", str(workspace),
            "--name", "Reference agent", "--provider", "chat-completions", "--model", "deterministic-reference",
            "--endpoint", model_server.url + "/v1/chat/completions", "--auth", "none"],
            check=True, capture_output=True, env=env)
        runtime_config = json.loads((runtime_home / "runtime.json").read_text())
        runtime_config["limits"]["max_model_calls"] = 40
        runtime_config["limits"]["max_context_bytes"] = 3000000
        runtime_config["limits"]["turn_seconds"] = 180
        # Fresh fixture configuration only, before any runtime process starts.
        save(runtime_home / "runtime.json", runtime_config)

        workshop = Installation("workshop", args.workshop, output, env)
        services.append(workshop)
        extractor = output / "extractor.json"
        save(extractor, {"command": sys.executable, "args": [str(args.extractor_fixture.resolve())],
            "cwd": str(workspace), "timeout_seconds": 30,
            "env": {"TWIN_FIXTURE_MODE": "normal", "TWIN_FIXTURE_DIR": str(output / "extraction")}})
        workshop.cli("init", "--owner", getpass.getuser(), "--bind", "127.0.0.1", "--port", "0", "--extractor-config", extractor, raw=True)
        workshop.start()
        descriptor = workshop.api("GET", "/api/v1/descriptor")
        assert "job-submission-recovery" in descriptor["capabilities"], descriptor
        project = workshop.api("POST", "/api/v1/projects", {"alias": "Fictional reference team", "aliases": ["Avery"],
            "subject_type": "fictional", "purpose": "Draft evidence-linked communication guidance for a fictional team; never apply it to a real person or agent."})
        project = workshop.api("POST", f"/api/v1/projects/{project['id']}/artifacts", {"expected_revision": project["revision"],
            "name": "Fictional working notes", "kind": "notes", "text": "Avery: Use concise, concrete language. Compare evidence before making a decision.",
            "authors": ["Avery"], "collections": ["communication", "working"]})
        accepted_tool_submissions = []
        def lose_tool_submission_reply(body):
            job = workshop.api("POST", f"/api/v1/projects/{project['id']}/builds", body)
            # Only independent fault-injection equipment sees this accepted ID.
            # The Tool adapter receives an actual HTTP disconnect, no job reply.
            accepted_tool_submissions.append({"operation": "build", "request_id": body["request_id"],
                "job_id": job["id"], "project_id": project["id"], "reply": "deliberately_lost"})
            return None
        tool_loss_proxy = LocalServer(lose_tool_submission_reply)
        servers.append(tool_loss_proxy)
        def submit_tool(body):
            connection = http.client.HTTPConnection("127.0.0.1", tool_loss_proxy.server.server_port, timeout=15)
            try:
                connection.request("POST", "/", json.dumps(body), {"Content-Type": "application/json"})
                return json.loads(connection.getresponse().read())
            finally:
                connection.close()
        adapter = WorkshopMCP(workshop.api, project, submit=submit_tool)
        tool_server = LocalServer(adapter.dispatch)
        servers.append(tool_server)

        instance = Installation("instance", args.instance, output, env)
        services.append(instance)
        instance.cli("init", "--name", "Reference agent", "--owner", getpass.getuser(), "--bind", "127.0.0.1", "--port", "0")
        token = instance.cli("token", "create", "--local", "--name", "reference-conversation", "--scopes", "acp,context:owner,tools:use")
        token_file = output / "attach-token"
        token_file.write_text(token["token"])
        token_file.chmod(0o600)
        instance.start()
        doc = instance.api("GET", "/api/v1/config")
        config = doc["config"]
        endpoints = json.loads((instance.home / "endpoints.json").read_text())
        config["server"]["public_url"] = endpoints["base_url"]
        backend_command = str(args.runtime.resolve())
        backend_args = ["--home", str(runtime_home), "acp"]
        if args.unified_python:
            unified = Installation("unified", args.unified_python, output, env)
            services.append(unified)
            unified.start([unified.binary, str(Path(__file__).with_name("unified_host.py")),
                "--home", str(unified.home), "--workspace", str(workspace), "--provider-url", model_server.url,
                "--ca-file", str(instance.home / "tls/root-ca.crt")], ready_file="ready.json", timeout=90)
            ready = json.loads((unified.home / "ready.json").read_text())
            backend_command = str(args.unified_python.absolute().with_name("amplifier-unified"))
            backend_args = ["--data-dir", str(unified.home / "app"), "--workspace", str(workspace), "acp",
                "--server", ready["url"], "--token-file", ready["token_file"], "--bundle", ready["bundle"]]
            report["unified"] = {k: v for k, v in ready.items() if k not in {"token_file"}}
        config.update({"setup_complete": True, "enabled": True,
            "backend": {"command": backend_command, "args": backend_args,
                        "env": {"SSL_CERT_FILE": str(instance.home / "tls/root-ca.crt")}, "secret_env": {}, "working_directory": str(workspace), "allowed_working_roots": [str(workspace)]},
            "tool_connections": [{"name": "workshop", "url": tool_server.url + "/mcp", "header_secrets": {}}]})
        instance.api("PUT", "/api/v1/config", {"expected_revision": doc["revision"], "config": config})

        conversations = Installation("conversations", args.conversations, output, env)
        services.append(conversations)
        port = free_port()
        attach_args = ["--home", str(instance.home), "acp", "--token-file", str(token_file)]
        conversations.cli("init", "--label", "Reference conversation", "--owner", getpass.getuser(),
            "--bind", "127.0.0.1", "--port", port, "--agent-command", args.instance.resolve(),
            *["--agent-arg=" + arg for arg in attach_args], "--agent-cwd", workspace, raw=True)
        cfg = conversations.cli("config", "get")
        cfg.update({"transport": "local_http", "auth_mode": "local_password", "public_url": f"http://127.0.0.1:{port}", "allowed_users": []})
        cfg["agent"]["timeout_seconds"] = 180
        cfg_path = output / "conversations-config.json"
        save(cfg_path, cfg)
        conversations.cli("config", "set", "--file", cfg_path, raw=True)
        conversations.start()
        credential = conversations.api("POST", "/api/v1/agents/default/context-credential", {})
        instance.api("PUT", "/api/v1/secrets/reference-source", {"value": credential["token"]})
        instance.api("PUT", "/api/v1/context/providers", {"providers": [{"id": credential["provider_id"],
            "label": "Reference conversation", "url": f"http://127.0.0.1:{port}/agents/default", "secret_ref": "reference-source"}]})
        room = conversations.api("POST", "/api/v1/conversations", {"title": "A fictional team communication brief"})
        room_id = room["id"]
        request_id, build_key = str(uuid.uuid4()), "reference-build-1"
        workshop_url = workshop.cli("status")["url"]
        def artifact_url(p):
            return f"{workshop_url}/api/v1/projects/{project['id']}/revisions/{p.results['recovered']['job']['result_id']}"
        def verified_command(p):
            recovered_job_oracle(accepted_tool_submissions, p.results["recovered"], project["id"], build_key)
            artifact_oracle(workshop, project["id"], p.results["recovered"]["job"]["result_id"])
            return {"type": "verify", "outcome": "pass", "evidence_ids": [e["id"] for e in p.results["reviewed"]["evidence"]],
                    "note": "The independent reference oracle read the saved Workshop export, checked its contents and verified manifest hashes before this verification."}
        create_args = lambda p: {"title": "Draft a fictional communication brief", "goal": "Produce an evidence-linked Workshop profile and return the artifact here.",
            "request_id": "reference-work-1", "source_input_id": p.source_input}
        review_args = lambda p: {"title": "Review the proposed brief later", "goal": "A separate proposed responsibility; do not begin it yet.",
            "request_id": "reference-work-2", "source_input_id": p.source_input}
        provider.set_plan([
            ("created", "work_create", create_args),
            ("same_creation", "work_create", create_args),
            ("review_proposal", "work_create", review_args),
            ("accepted", "work_command", command("created", {"type": "accept"})),
            ("started", "work_command", command("accepted", {"type": "start"})),
            ("build_lost", "profile_build", {"request_id": build_key}),
            ("recovered", "profile_inspect", {"request_id": build_key}),
            ("evidence", "work_command", command("started", lambda p: {"type": "evidence", "kind": "artifact",
                "label": "Workshop profile revision", "uri": artifact_url(p)})),
            ("reviewed", "work_command", command("evidence", {"type": "review"})),
            ("verified", "work_command", command("reviewed", verified_command)),
            ("completed", "work_command", command("verified", {"type": "complete"})),
            {"final": lambda p: "The fictional team's communication brief is ready. It recommends concise, concrete language and checking evidence before deciding. "
                + f"Work {p.results['completed']['id']} is complete after the reference oracle checked the saved artifact: {artifact_url(p)}. "
                + "This is synthetic guidance, not an assessment of a real person."},
        ])
        publication = {"text": "Draft a communication brief from the fictional Avery notes using Workshop. Accept responsibility, keep the evidence, and bring the result back here. Also record a separate review proposal for later, without starting that review yet.", "request_id": request_id}
        # Send a complete source request, then close before reading its HTTP reply.
        # We recover by the original UUID, never by posting the source again.
        def lose_source_reply(body):
            conversations.api("POST", f"/api/v1/conversations/{room_id}/messages", body)
            return None
        loss_proxy = LocalServer(lose_source_reply)
        servers.append(loss_proxy)
        connection = http.client.HTTPConnection("127.0.0.1", loss_proxy.server.server_port, timeout=10)
        connection.request("POST", "/", json.dumps(publication), {"Content-Type": "application/json"})
        try:
            connection.getresponse()
            raise AssertionError("The fault proxy unexpectedly returned the acceptance reply")
        except http.client.RemoteDisconnected:
            pass
        finally:
            connection.close()
        settled = wait_turn(conversations, room_id, provider)
        exact = conversations.api("GET", f"/api/v1/conversations/{room_id}/deliveries?request_id={request_id}")
        assert exact["publication"]["state"] == "saved", exact
        original_delivery = next(row for row in exact["items"] if row["agent_id"] == "default")
        source_fact = original_delivery["source_delivery"]
        assert source_fact["status"] == "observed", source_fact
        receipt = source_fact["receipt"]["receipts"][0]
        assert receipt["completion"] == "not_established", receipt
        assert {w["id"] for w in receipt["work"]} == {provider.results["created"]["id"], provider.results["review_proposal"]["id"]}, receipt
        assert provider.results["created"]["id"] == provider.results["same_creation"]["id"]
        assert provider.results["created"]["id"] != provider.results["review_proposal"]["id"]
        checks.append({"name": "lost_source_reply_exact_lookup", "pass": True, "request_id": request_id})
        checks.append({"name": "creation_retry_same_record", "pass": True})
        checks.append({"name": "one_source_two_authorized_responsibilities", "pass": True})
        checks.append({"name": "source_receipt_correlates_both_work_records_without_claiming_fulfillment", "pass": True})
        assert len([e for e in adapter.events if e["operation"] == "build"]) == 1
        recovered = provider.results["recovered"]
        assert tool_failed(provider.raw_results["build_lost"]) is True
        assert provider.results["build_lost"]["acceptance"] == "unknown"
        recovered_job_oracle(accepted_tool_submissions, recovered, project["id"], build_key)
        checks.append({"name": "lost_workshop_submission_reply_inspect_without_reinvoke", "pass": True, "job_id": recovered["job"]["id"]})
        work = instance.api("GET", "/api/v1/work/" + provider.results["created"]["id"])
        assert work["state"] == "completed", work
        assert work["source_input"]["inputId"] == provider.source_input
        assert work["source"]["conversation_id"] == room_id
        identity_chain = source_identity_oracle(exact, settled, request_id, work, publication["text"])
        proposed_review = instance.api("GET", "/api/v1/work/" + provider.results["review_proposal"]["id"])
        source_identity_oracle(exact, settled, request_id, proposed_review, publication["text"])
        checks.append({"name": "original_publication_delivery_receipt_and_work_identity_chain", "pass": True})
        # Source-owned publication, receipt, actual work, and real Tool artifact
        # are independently read here; the fixture's final sentence is not proof.
        profile = artifact_oracle(workshop, project["id"], recovered["job"]["result_id"])
        final_message = next(m for m in reversed(settled["messages"]) if m["role"] == "assistant" and m["status"] == "complete")
        assert work["id"] in final_message["text"] and artifact_url(provider) in final_message["text"]
        assert "concise, concrete language" in final_message["text"]
        checks.append({"name": "independent_artifact_and_work_oracle", "pass": True, "work_id": work["id"]})
        # A second source-owned browser view points at the same conversation.
        views = []
        for _ in range(2):
            view = str(uuid.uuid4())
            conversations.api("PUT", "/api/v1/views/" + view, {"expected_revision": 0,
                "state": {"selected_conversation_id": room_id, "panel": "conversation", "draft": "", "search": ""}})
            views.append(conversations.api("GET", "/api/v1/views/" + view))
        assert all(v["state"]["selected_conversation_id"] == room_id for v in views)
        checks.append({"name": "two_views_same_source_conversation", "pass": True})

        original_input = provider.source_input
        frozen_review_args = {**review_args(provider), "source_input_id": original_input}
        unknown_key = "never-submitted-" + str(uuid.uuid4())
        provider.set_plan([
            ("review_accepted", "work_command", command("review_proposal", {"type": "accept"})),
            ("review_amended", "work_command", command("review_accepted", {"type": "amend",
                "title": "Check accessibility wording", "goal": "Review accessibility wording only."})),
            ("review_stopped", "work_command", command("review_amended", {"type": "cancel", "reason": "The requester explicitly stopped this review."})),
            ("retry_after_stop", "work_create", frozen_review_args),
            ("conflicting_retry", "work_create", {**frozen_review_args, "goal": "A different responsibility under the same creation key"}),
            ("unknown_job", "profile_inspect", {"request_id": unknown_key}),
            "The separate review was amended, then stopped as requested. Its original record is retained. No replacement review or unknown Workshop operation was started.",
        ])
        conversations.api("POST", f"/api/v1/conversations/{room_id}/messages", {"request_id": str(uuid.uuid4()),
            "text": "For the reference control check, accept the separate review, narrow it to accessibility wording, then stop it. Inspect the original creation and an unknown tool request without starting anything again."})
        controls = wait_turn(conversations, room_id, provider)
        stopped = instance.api("GET", "/api/v1/work/" + provider.results["review_proposal"]["id"])
        assert stopped["state"] == "cancelled" and stopped["title"] == "Check accessibility wording", stopped
        assert provider.results["retry_after_stop"]["id"] == stopped["id"]
        assert provider.results["retry_after_stop"]["state"] == "cancelled"
        refused = provider.results["conflicting_retry"]
        assert tool_failed(provider.raw_results["conflicting_retry"]) is True, provider.raw_results["conflicting_retry"]
        assert not isinstance(refused, dict) or refused.get("id") != stopped["id"], refused
        assert provider.results["unknown_job"] == {"outcome": "unknown", "job": None}, provider.results["unknown_job"]
        assert len([e for e in adapter.events if e["operation"] == "build"]) == 1
        checks.extend([{"name": "amend_and_stop_same_work", "pass": True},
            {"name": "creation_retry_preserves_stopped_record", "pass": True},
            {"name": "changed_creation_key_payload_refused", "pass": True},
            {"name": "unknown_tool_job_not_replayed", "pass": True}])
        before_inspection_calls = len(provider.events)
        conversations.api("POST", f"/api/v1/conversations/{room_id}/deliveries/{original_delivery['id']}/inspect", {})
        refreshed = conversations.api("GET", f"/api/v1/conversations/{room_id}/deliveries?request_id={request_id}")
        current = next(row for row in refreshed["items"] if row["agent_id"] == "default")["source_delivery"]
        assert current["sources"] == source_fact["sources"]
        assert {w["id"]: w["state"] for w in current["receipt"]["receipts"][0]["work"]} == {work["id"]: "completed", stopped["id"]: "cancelled"}
        assert len(provider.events) == before_inspection_calls, "Receipt inspection unexpectedly prompted the engine"
        checks.append({"name": "original_source_inspection_loads_without_prompt_or_replay", "pass": True})

        # Add an uninvoked reference peer to a separate room so this conversation
        # has a shared audience. Only the original Instance receives a prompt.
        peer = dict(cfg["agent"])
        peer.update({"label": "Uninvoked reference peer", "command": str(args.runtime.resolve()),
                     "args": ["--home", str(runtime_home), "acp"]})
        conversations.api("POST", "/api/v1/agents", {"id": "reference-peer", "config": peer})
        other_room = conversations.api("POST", "/api/v1/conversations", {"title": "Separate shared audience",
            "agent_ids": ["default", "reference-peer"]})
        provider.set_plan([
            ("wrong_audience", "work_get", {"id": work["id"]}),
            "That responsibility is not available in this conversation's audience. I have not copied its private contents here.",
        ])
        conversations.api("POST", f"/api/v1/conversations/{other_room['id']}/messages", {"request_id": str(uuid.uuid4()),
            "target_agent_ids": ["default"], "text": "For the reference boundary check, inspect the separately scoped work ID only if this room is authorized; otherwise report that it is unavailable."})
        audience_room = wait_turn(conversations, other_room["id"], provider)
        denied = provider.results["wrong_audience"]
        assert tool_failed(provider.raw_results["wrong_audience"]) is True, provider.raw_results["wrong_audience"]
        assert not isinstance(denied, dict) or denied.get("id") != work["id"], denied
        assert work["goal"] not in json.dumps(audience_room["messages"])
        checks.append({"name": "wrong_audience_cannot_read_work", "pass": True})

        # Accepted work can survive a failed reply. Leave the delivery unknown;
        # inspect its work reference without acknowledging or replaying input.
        recovery_room = conversations.api("POST", "/api/v1/conversations", {"title": "Acceptance reply interrupted"})
        recovery_request = str(uuid.uuid4())
        provider.set_plan([
            ("recovery_created", "work_create", lambda p: {"title": "A retained responsibility", "goal": "Accept this responsibility but do not begin external work.",
                "request_id": "accepted-before-reply-failure", "source_input_id": p.source_input}),
            ("recovery_accepted", "work_command", command("recovery_created", {"type": "accept"})),
            {"failure": "Deliberate failure after accepted work was recorded, before any final response."},
        ])
        conversations.api("POST", f"/api/v1/conversations/{recovery_room['id']}/messages", {"request_id": recovery_request,
            "text": "Record and accept responsibility for this reference check. Do not begin external work; we are testing recovery if the response fails."})
        interrupted = wait_turn(conversations, recovery_room["id"], provider, expect_failure=True)
        accepted = instance.api("GET", "/api/v1/work/" + provider.results["recovery_created"]["id"])
        assert accepted["state"] == "accepted", accepted
        prior = conversations.api("GET", f"/api/v1/conversations/{recovery_room['id']}/deliveries?request_id={recovery_request}")
        recovery_delivery = prior["items"][0]
        assert recovery_delivery["state"] == "unknown", recovery_delivery
        before_recovery_calls = len(provider.events)
        conversations.api("POST", f"/api/v1/conversations/{recovery_room['id']}/deliveries/{recovery_delivery['id']}/inspect", {})
        recovery = conversations.api("GET", f"/api/v1/conversations/{recovery_room['id']}/deliveries?request_id={recovery_request}")
        after_delivery = recovery["items"][0]
        assert after_delivery["state"] == "unknown", after_delivery
        retained = after_delivery["source_delivery"]["receipt"]["receipts"][0]
        assert retained["completion"] == "not_established" and retained["work"][0]["id"] == accepted["id"]
        assert retained["work"][0]["state"] == "accepted"
        assert len(provider.events) == before_recovery_calls
        assert len([e for e in adapter.events if e["operation"] == "build"]) == 1
        checks.append({"name": "lost_acceptance_response_recovers_same_work_without_source_replay", "pass": True})

        # A separately launched client reads the actual saved records and emits
        # an inspection surface. It shares no provider state with this driver.
        before_second_client = len(provider.events)
        subprocess.run([sys.executable, str(Path(__file__).with_name("inspect_view.py")),
            "--conversations", conversations.binary, "--conversations-home", str(conversations.home),
            "--instance", instance.binary, "--instance-home", str(instance.home),
            "--conversation", room_id, "--request", request_id, "--work", work["id"],
            "--output", str(output / "inspect")], env=env, check=True, capture_output=True, text=True, timeout=45)
        inspected = json.loads((output / "inspect.json").read_text())
        assert inspected["conversation_id"] == room_id and inspected["work_id"] == work["id"]
        assert len(provider.events) == before_second_client
        checks.append({"name": "second_read_only_client_inspects_same_conversation_and_work", "pass": True})
        report["binary_hashes_after"] = {name: digest(getattr(args, name)) for name in report["binaries"]}
        assert all(report["binary_hashes_after"][name] == value["sha256"] for name, value in report["binaries"].items())

        report.update({"conversation_id": room_id, "source_request_id": request_id,
            "work_id": work["id"], "tool_job_id": recovered["job"]["id"], "source": exact, "identity_chain": identity_chain,
            "source_after_controls": refreshed,
            "work": work, "tool": recovered, "messages": settled["messages"], "views": views,
            "control_messages": controls["messages"], "stopped_review": stopped,
            "audience_check": {"conversation_id": other_room["id"], "result": denied},
            "lost_acceptance": {"source": recovery, "work": accepted, "messages": interrupted["messages"]},
            "second_client": inspected, "tool_trace": adapter.events, "tool_submission_fault_trace": accepted_tool_submissions,
            "provider_trace": provider.events})
        save(output / "result.json", report)
        (output / "report.html").write_text("<!doctype html><meta charset=utf-8><title>Five primitives reference</title>"
            "<h1>A request becomes inspectable work</h1><p>Deterministic composition proof; no real model or production operation.</p>"
            "<p>Experience → source-owned Conversation → Connection → Agent Instance → Workshop Tool → the original conversation.</p>"
            "<pre>" + html.escape(json.dumps(report, indent=2)) + "</pre>")
        print(json.dumps({"result": str(output / "result.json"), "report": str(output / "report.html"), "checks": checks}, indent=2))
    except BaseException as error:
        save(output / "failure.json", {"kind": type(error).__name__, "detail": str(error),
            "checks_completed": checks, "engine": report["engine"], "actual_model_coverage": False})
        raise
    finally:
        save(output / "provider-events.json", provider.events)
        for service in reversed(services):
            service.close()
        for server in reversed(servers):
            server.close()
        trace.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("instance", "runtime", "conversations", "workshop", "extractor-fixture", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--unified-python", type=Path, help="Optional isolated Unified worker interpreter; selects the explicit MCP fixture profile instead of Native.")
    main(parser.parse_args())
