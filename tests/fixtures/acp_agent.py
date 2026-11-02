#!/usr/bin/env python3
"""Deterministic protocol fixture. It is never presented as a real model."""
import argparse
import json
from pathlib import Path
import sys
import uuid

p = argparse.ArgumentParser()
p.add_argument("--home", type=Path, required=True)
p.add_argument("--mode", default="normal")
args = p.parse_args()
args.home.mkdir(parents=True, exist_ok=True)


def send(value):
    print(json.dumps({"jsonrpc": "2.0", **value}), flush=True)


def chunk(session, text):
    send({"method": "session/update", "params": {"sessionId": session,
        "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}}}})


ARTIFACT = '''def profile_status(installed, supplied, turn_state):
    if installed is None or supplied is None:
        return "unknown"
    if turn_state in ("in_progress", "interrupted"):
        return "partial"
    if turn_state == "completed":
        if installed == supplied:
            return "current"
        return "previous"
    return "unknown"
'''

for line in sys.stdin:
    message = json.loads(line)
    with (args.home / "requests.jsonl").open("a") as stream:
        stream.write(json.dumps(message) + "\n")
    method, request_id, params = message.get("method"), message.get("id"), message.get("params", {})
    if method == "initialize":
        send({"id": request_id, "result": {"protocolVersion": 1,
              "agentInfo": {"name": "protocol-fixture", "version": "1"},
              "agentCapabilities": {"loadSession": args.mode != "no_load"}, "authMethods": []}})
    elif method == "session/new":
        session = str(uuid.uuid4())
        (args.home / session).touch()
        send({"id": request_id, "result": {"sessionId": session}})
    elif method == "session/load":
        session = params["sessionId"]
        if not (args.home / session).exists():
            send({"id": request_id, "error": {"code": -32602, "message": "Unknown session"}})
        else:
            # Replay must never become a new visible contribution.
            chunk(session, "A replayed historical response, not a new turn.")
            send({"id": request_id, "result": {}})
    elif method == "session/prompt":
        session = params["sessionId"]
        text = params["prompt"][0]["text"]
        context = json.loads(text.split("\n\n", 1)[1])
        if args.mode == "recheck_disconnect" and "publication_review" in context:
            sys.exit(0)
        if args.mode == "disconnect":
            sys.exit(0)
        if args.mode == "permission":
            send({"id": "permission-1", "method": "session/request_permission", "params": {"sessionId": session, "toolCall": {"toolCallId": "tool-1"}, "options": []}})
            response = json.loads(sys.stdin.readline())
            assert response["result"]["outcome"]["outcome"] == "cancelled"
            send({"method": "session/update", "params": {"sessionId": session, "update": {"sessionUpdate": "tool_call", "toolCallId": "tool-1", "title": "fixture tool", "status": "failed"}}})
        if args.mode == "foreign_session":
            chunk("not-this-session", "leak")
            continue
        cues = [item["text"] for item in context["history"] if item["kind"] == "operator_cue"]
        latest = cues[-1] if cues else ""
        if "INTERRUPT" in latest and "REVISED" not in latest and args.mode != "quick":
            chunk(session, '{"action":"speak","text":"STALE PRIVATE DRAFT')
            while True:
                incoming = json.loads(sys.stdin.readline())
                if incoming.get("method") == "session/cancel":
                    break
            if args.mode == "ignore_cancel":
                # Wait until the client timeout closes this disposable process.
                sys.stdin.read()
                continue
            chunk(session, '"}')
            send({"id": request_id, "result": {"stopReason": "cancelled"}})
            continue
        if "REVISED" in latest:
            receipts = context["response_delivery"]["items"]
            hidden = any(item["delivery"] == "not_delivered" for item in receipts)
            assert not any("STALE PRIVATE DRAFT" in item["text"] for item in context["history"])
            reply = f"Revised goal considered. Earlier private draft receipt present: {hidden}."
        elif "ARTIFACT" in latest:
            reply = "Here is the exact artifact for independent checking.\n```python\n" + ARTIFACT + "```"
        else:
            reply = f"Contribution from {context['your_participant_id']} in {context['room']}."
        if args.mode == "pass" or (args.mode == "after_peer" and any(item["kind"] == "protocol_fixture" and item["speaker"] != context["your_participant_id"] for item in context["history"])):
            output = json.dumps({"action": "pass", "reason": "No new contribution"})
        elif args.mode == "plain":
            output = "A natural language reply."
        elif args.mode == "malformed":
            output = '{"badly formed'
        else:
            output = json.dumps({"action": "speak", "text": reply})
        if args.mode == "progress":
            chunk(session, "Private progress update before the final contribution.\n")
        chunk(session, output)
        send({"id": request_id, "result": {"stopReason": "end_turn"}})
    elif request_id is not None:
        send({"id": request_id, "error": {"code": -32601, "message": "Not supported"}})
