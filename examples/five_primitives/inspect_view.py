#!/usr/bin/env python3
"""A second read-only client for the disposable reference's existing records.

The component CLIs authenticate to their own local installations. This client
never prompts an agent, creates a conversation, or reconciles an unknown effect.
"""
import argparse
import html
import json
from pathlib import Path
import subprocess
from oracles import source_identity_oracle


def get(binary, home, path):
    result = subprocess.run([str(binary), "--home", str(home), "api", "GET", path],
                            capture_output=True, text=True, check=True, timeout=30)
    return json.loads(result.stdout)


def inspect(args):
    room = get(args.conversations, args.conversations_home,
               f"/api/v1/conversations/{args.conversation}")
    source = get(args.conversations, args.conversations_home,
                 f"/api/v1/conversations/{args.conversation}/deliveries?request_id={args.request}")
    work = get(args.instance, args.instance_home, f"/api/v1/work/{args.work}")
    identity_chain = source_identity_oracle(source, room, args.request, work)
    linked = {ref["id"] for row in source["items"]
              for receipt in row.get("source_delivery", {}).get("receipt", {}).get("receipts", [])
              for ref in receipt.get("work", [])}
    assert args.work in linked
    assert room["id"] == args.conversation == work["source"]["conversation_id"]
    result = next(message for message in room["messages"] if message["role"] == "assistant"
                  and args.work in message["text"] and message["status"] == "complete")
    assert work["state"] == "completed"
    facts = {"kind": "second_read_only_reference_client", "conversation_id": room["id"],
             "source_request_id": args.request, "linked_work_ids": sorted(linked),
             "work_id": work["id"], "work_state": work["state"], "message": result,
             "source": source, "identity_chain": identity_chain, "prompts_sent": 0, "mutations": 0}
    args.output.with_suffix(".json").write_text(json.dumps(facts, indent=2) + "\n")
    args.output.with_suffix(".html").write_text(
        "<!doctype html><html lang=en><meta charset=utf-8><title>Inspect the original work</title>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<style>body{font:18px/1.6 system-ui;max-width:48rem;margin:3rem auto;padding:0 1rem}"
        "pre{font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}</style>"
        "<h1>The result, in its original conversation</h1><p>" + html.escape(result["text"]) + "</p>"
        "<p>This separate reference client read the same saved conversation, source receipt and work record. "
        "It sent no agent prompt and changed no record.</p><details><summary>Inspect the records</summary><pre>"
        + html.escape(json.dumps(facts, indent=2)) + "</pre></details></html>")
    print(json.dumps({"conversation_id": room["id"], "work_id": work["id"], "prompts_sent": 0, "mutations": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("conversations", "conversations-home", "instance", "instance-home", "output"):
        parser.add_argument("--" + key, required=True, type=Path)
    for key in ("conversation", "request", "work"):
        parser.add_argument("--" + key, required=True)
    inspect(parser.parse_args())
