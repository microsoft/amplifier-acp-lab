#!/usr/bin/env python3
"""Produce a browsable report from ACP process fixtures, without model calls."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiment_lab.analysis import evaluate, report
from experiment_lab.engine import Engine
from experiment_lab.scenario import validate
from experiment_lab.storage import Run

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--output", type=Path, required=True)
args = p.parse_args()
output = args.output.resolve()
scenario = validate({
    "schema": "agent-experiment-lab.scenario/1", "label": "Protocol fixture — delivery-aware interruption and exact artifact",
    "participants": {key: {"label": key + " protocol fixture", "kind": "protocol_fixture"} for key in ("one", "two", "reviewer")},
    "rooms": {"product": {"members": ["one", "two"]}, "side-room": {"members": ["one"]}},
    "steps": [
        {"action": "cue", "room": "product", "text": "Discuss this product."},
        {"action": "round", "room": "product"},
        {"action": "cue", "room": "side-room", "text": "Private side-room context stays here."},
        {"action": "round", "room": "side-room"},
        {"action": "join", "room": "product", "participant": "reviewer"},
        {"action": "cue", "room": "product", "text": "INTERRUPT this draft"},
        {"action": "round", "room": "product", "participants": ["one"], "interrupt": {"when": "first_chunk", "participant": "one", "text": "REVISED criterion: reopen work before publishing"}},
        {"action": "round", "room": "product"},
        {"action": "cue", "room": "product", "text": "ARTIFACT: publish the pure function for separate operator verification."},
        {"action": "round", "room": "product", "participants": ["one"]},
    ],
    "evaluators": [{"id": "profile-status", "room": "product", "language": "python", "command": [sys.executable, str(ROOT / "examples/evaluate_status.py")]}],
})
bindings = {"schema": "agent-experiment-lab.bindings/1", "participants": {
    key: {"command": [sys.executable, str(ROOT / "tests/fixtures/acp_agent.py"), "--home", str(output.parent / (output.name + "-endpoints") / key)], "cwd": str(output.parent)}
    for key in scenario["participants"]}}
run = Run.create(output, scenario, bindings)
with run.lock():
    asyncio.run(Engine(run).execute())
    evaluate(run, "profile-status")
    result = report(run)
print(json.dumps({"experience": "protocol_fixture", "model_calls": 0, "report": str(output / "report.html"), "measurements": result["measurements"]}, indent=2))
