"""All experiment controls are available through JSON files and this CLI."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from .analysis import compare, evaluate, report
from .batch import batch
from .engine import Engine, resolve
from .imports import import_slack
from .network import api, submit
from .scenario import validate, validate_bindings
from .storage import Run, digest, now, read
from .suite import prepare, run_suite, suite_report


def parser():
    p = argparse.ArgumentParser(description="Repeatable independent-agent collaboration experiments")
    sub = p.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("validate", help="Validate and describe a scenario without starting agents")
    plan.add_argument("scenario", type=Path)
    plan.add_argument("--bindings", type=Path)
    start = sub.add_parser("run", help="Create and execute a run through ordinary ACP endpoints")
    start.add_argument("scenario", type=Path)
    start.add_argument("--bindings", required=True, type=Path)
    start.add_argument("--output", required=True, type=Path)
    start.add_argument("--max-steps", type=int)
    resume = sub.add_parser("resume", help="Continue a checkpoint without replaying finished or uncertain prompts")
    resume.add_argument("run", type=Path)
    resume.add_argument("--max-steps", type=int)
    for name in ("report", "inspect", "unlock"):
        item = sub.add_parser(name)
        item.add_argument("run", type=Path)
        if name == "unlock":
            item.add_argument("--reason", required=True)
    skip = sub.add_parser("resolve", help="Record operator inspection and skip an uncertain turn; never replay it")
    skip.add_argument("run", type=Path)
    skip.add_argument("--turn", required=True)
    skip.add_argument("--reason", required=True)
    ev = sub.add_parser("evaluate", help="Run a scenario's explicitly configured operator evaluator")
    ev.add_argument("run", type=Path)
    ev.add_argument("--evaluator", required=True)
    comp = sub.add_parser("compare")
    comp.add_argument("runs", nargs="+", type=Path)
    comp.add_argument("--output", type=Path, required=True)
    matrix = sub.add_parser("batch", help="Run a scenario matrix with bounded concurrent clients")
    matrix.add_argument("manifest", type=Path)
    matrix.add_argument("--output", type=Path, required=True)
    freeze = sub.add_parser("suite-prepare", help="Freeze cases, expectations and policy conditions without model calls")
    freeze.add_argument("manifest", type=Path)
    freeze.add_argument("--bindings", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument("--split", choices=("calibration", "held_out", "all"), default="held_out")
    freeze.add_argument("--repetitions", type=int, default=1)
    freeze.add_argument("--max-parallel", type=int, default=1)
    for name in ("suite-run", "suite-report"):
        item = sub.add_parser(name)
        item.add_argument("directory", type=Path)
    imp = sub.add_parser("import-slack", help="Read a recorded trial without making network calls")
    imp.add_argument("source", type=Path)
    imp.add_argument("--output", type=Path, required=True)
    feedback = sub.add_parser("feedback", help="Record actual human feedback, attributed to its source")
    feedback.add_argument("run", type=Path)
    feedback.add_argument("--observer", required=True)
    feedback.add_argument("--source", required=True, help="Reference to actual human statement/observation")
    feedback.add_argument("--text", required=True)
    feedback.add_argument("--human-observation", action="store_true", required=True)
    snapshot = sub.add_parser("observe", help="Capture a read-only management observation from an optional API")
    snapshot.add_argument("run", type=Path)
    snapshot.add_argument("--url", required=True)
    snapshot.add_argument("--token-file", required=True, type=Path)
    snapshot.add_argument("--path", required=True)
    fleet = sub.add_parser("submit", help="Submit this report to an optional fleet manager")
    fleet.add_argument("run", type=Path)
    fleet.add_argument("--url", required=True)
    fleet.add_argument("--token-file", required=True, type=Path)
    fleet.add_argument("--report-url")
    fleet.add_argument("--include-transcript", action="store_true", help="Also publish delivered room messages, with simulation/operator labels; excludes private drafts and prompts")
    return p


def load_scenario(path):
    value = read(path)
    # A stable absolute path is captured in the manifest and hashed for later
    # comparison; evaluation never depends on the runner's current directory.
    for evaluator in value.get("evaluators", []):
        evaluator["command"] = [arg.replace("${SCENARIO_DIR}", str(path.resolve().parent)).replace("${PYTHON}", sys.executable) for arg in evaluator.get("command", [])]
    return validate(value)


def execute(args):
    if args.command == "suite-prepare":
        return prepare(args.manifest, args.bindings, args.output, load_scenario, args.split, args.repetitions, args.max_parallel)
    if args.command in ("suite-run", "suite-report"):
        result = asyncio.run(run_suite(args.directory)) if args.command == "suite-run" else suite_report(args.directory)
        return {"report": str(args.directory.resolve() / "report.html"), "split": result["split"], "totals": result["totals"]}
    if args.command == "validate":
        scenario = load_scenario(args.scenario)
        if args.bindings:
            validate_bindings(read(args.bindings), scenario)
        return {"valid": True, "scenario_sha256": digest(scenario), "participants": list(scenario["participants"]),
                "steps": len(scenario["steps"]), "model_calls": 0}
    if args.command == "compare":
        return compare([Run(path) for path in args.runs], args.output)
    if args.command == "batch":
        return asyncio.run(batch(args.manifest, args.output, load_scenario))
    if args.command == "import-slack":
        return report(import_slack(args.source, args.output))
    if args.command == "run":
        scenario = load_scenario(args.scenario)
        bindings = validate_bindings(read(args.bindings), scenario)
        run = Run.create(args.output, scenario, bindings)
    else:
        run = Run(args.run)
    if args.command == "inspect":
        return {"run_id": run.data["id"], "status": run.data["status"], "cursor": run.data["cursor"],
                "uncertain_turns": [{key: turn.get(key) for key in ("id", "participant", "room", "state", "delivery", "reason")} for turn in run.data["turns"] if turn["state"] in ("unknown", "in_flight", "connecting", "connection_error")],
                "lock": read(run.path / ".runner.lock") if (run.path / ".runner.lock").exists() else None}
    if args.command == "unlock":
        previous = read(run.path / ".runner.lock")
        if not args.reason.strip():
            raise ValueError("Record why the prior process is known to have stopped")
        (run.path / ".runner.lock").unlink()
        run.event("operator_unlock", previous=previous, reason=args.reason)
        return {"unlocked": True}
    with run.lock():
        if args.command in ("run", "resume"):
            if args.max_steps is not None and args.max_steps < 1:
                raise ValueError("max-steps must be positive")
            asyncio.run(Engine(run).execute(args.max_steps))
        elif args.command == "resolve":
            resolve(run, args.turn, args.reason)
        elif args.command == "evaluate":
            evaluate(run, args.evaluator)
        elif args.command == "feedback":
            run.data["human_feedback"].append({"observer": args.observer, "source": args.source, "text": args.text,
                                                "recorded_at": now(), "origin": "operator_recorded_human_observation",
                                                "observer_identity_independently_verified": False})
            run.save()
        elif args.command == "observe":
            value = api(args.url, args.token_file, args.path)
            evidence = run.evidence(f'observation-{len(run.data["observations"]) + 1}.json', value)
            run.data["observations"].append({"origin": args.url, "resource": args.path, "at": now(), "evidence": evidence, "classification": "reported_by_management_api"})
            run.save()
        summary = report(run)
        if args.command == "submit":
            return submit(run, summary, args.url, args.token_file, args.report_url, args.include_transcript)
    return {"run_id": run.data["id"], "status": run.data["status"], "run": str(run.path),
            "report": str(run.path / "report.html"), "measurements": summary["measurements"]}


def main():
    os.umask(0o077)
    args = parser().parse_args()
    try:
        result = execute(args)
    except Exception as error:
        # HTTP and endpoint exception text can contain URLs or credentials. The
        # local evidence and endpoint logs supply details without console leaks.
        message = str(error) if isinstance(error, ValueError) else "Operation failed; inspect private run evidence and endpoint logs"
        print(json.dumps({"error": type(error).__name__, "message": message}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 2 if isinstance(result, dict) and result.get("status") == "needs_resolution" else 0


if __name__ == "__main__":
    raise SystemExit(main())
