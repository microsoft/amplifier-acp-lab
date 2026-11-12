"""Freeze attention cases before execution and score every planned opportunity.

Expected actions are operator hypotheses, not naturalness labels or model input.
Missing/failed turns never earn silence credit. New cases require a new plan.
"""
import asyncio
from collections import Counter
import copy
import html
from pathlib import Path

from .analysis import STYLE, evaluate, report
from .attention import validate_attention
from .engine import Engine
from .scenario import ID, require, validate, validate_bindings
from .platform import private_directory
from .storage import write_bytes, Run, digest, driver_identity, now, read, write


def validate_expectations(scenario, expectations):
    require(isinstance(expectations, list) and expectations, "Each case needs expected decisions")
    seen = set()
    planned, members = set(), {room: value["members"][:] for room, value in scenario["rooms"].items()}
    for index, step in enumerate(scenario["steps"]):
        if step["action"] == "join":
            members[step["room"]].append(step["participant"])
        elif step["action"] == "leave":
            members[step["room"]].remove(step["participant"])
        elif step["action"] == "round":
            planned.update((index, participant) for participant in step.get("participants", members[step["room"]]))
    for item in expectations:
        pair = (item.get("step"), item.get("participant"))
        require(pair in planned and pair not in seen, "Expectations must uniquely identify planned opportunities")
        seen.add(pair)
        require(item.get("expected") in ("speak", "pass", "cancelled", "optional"), "Invalid expected decision")
        require(ID.fullmatch(item.get("category", "")), "Expectation needs a category")
    require(seen == planned, "Every planned opportunity needs a scored or explicitly optional expectation")


def prepare(manifest_path, bindings_path, output, loader, split="held_out", repetitions=1, max_parallel=1):
    manifest_path, output = Path(manifest_path).resolve(), Path(output).resolve()
    manifest, bindings = read(manifest_path), read(bindings_path)
    require(manifest.get("schema") == "agent-experiment-lab.attention-suite/1", "Unsupported attention suite")
    require(split in ("calibration", "held_out", "all"), "Invalid suite split")
    require(type(repetitions) is int and 1 <= repetitions <= 10, "Use 1–10 repetitions")
    require(type(max_parallel) is int and 1 <= max_parallel <= 4, "Use 1–4 parallel cases")
    conditions = manifest.get("conditions", {})
    ordering = manifest.get("participant_order", "declared")
    require(ordering in ("declared", "rotate"), "Participant order must be declared or rotate")
    require(isinstance(conditions, dict) and 1 <= len(conditions) <= 8, "Use 1–8 explicit conditions")
    for name in conditions:
        require(ID.fullmatch(name), "Invalid condition ID")
        conditions[name] = validate_attention(conditions[name])
    cases = manifest.get("cases", [])
    require(isinstance(cases, list) and 1 <= len(cases) <= 40, "Use 1–40 cases")
    require(len({case["id"] for case in cases}) == len(cases), "Case IDs must be unique")
    frozen = []
    for case in cases:
        require(ID.fullmatch(case.get("id", "")), "Invalid case ID")
        require(case.get("split") in ("calibration", "held_out"), "Cases must declare calibration or held_out")
        scenario = loader(manifest_path.parent / case["scenario"])
        validate_bindings(bindings, scenario)
        validate_expectations(scenario, case.get("expectations"))
        for window in case.get("response_windows", []):
            step = window.get("step")
            require(type(step) is int and 0 <= step < len(scenario["steps"]) and scenario["steps"][step]["action"] == "round", "Response window needs a round")
            require(type(window.get("min_speakers")) is int and type(window.get("max_speakers")) is int and 0 <= window["min_speakers"] <= window["max_speakers"] <= 16, "Invalid response window")
        frozen.append({**case, "scenario": scenario, "scenario_sha256": digest(scenario)})
    selected = [case for case in frozen if split == "all" or case["split"] == split]
    require(bool(selected), "No cases in selected split")
    require(not output.exists(), "A new suite needs a new output directory")
    private_directory(output, exist_ok=False)
    # Include the unexecuted split: later readers can verify that held-out cases
    # were already fixed before calibration outputs became available.
    snapshot = {"manifest": manifest, "cases": frozen, "created_at": now(), "driver": driver_identity()}
    write(output / "frozen-suite.json", snapshot)
    entries, names = [], list(conditions)
    for repetition in range(1, repetitions + 1):
        for index, case in enumerate(selected):
            offset = (index + repetition - 1) % len(names)
            for condition_id in names[offset:] + names[:offset]:
                scenario = copy.deepcopy(case["scenario"])
                scenario["attention"] = conditions[condition_id]
                if ordering == "rotate":
                    # The same order in each condition of a repetition. Rotate
                    # each explicit round and the room defaults across repeats.
                    for room in scenario["rooms"].values():
                        members = room["members"]
                        shift = (repetition - 1) % len(members) if members else 0
                        room["members"] = members[shift:] + members[:shift]
                    for step in scenario["steps"]:
                        if step["action"] == "round" and step.get("participants"):
                            members = step["participants"]
                            shift = (repetition - 1) % len(members)
                            step["participants"] = members[shift:] + members[:shift]
                scenario["label"] = f'{case["id"]} · {condition_id} · {repetition}'
                scenario = validate(scenario)
                name = f'{case["id"]}-{condition_id}-{repetition:02d}'
                run = Run.create(output / name, scenario, bindings)
                run.data["attention_trial"] = {"case_id": case["id"], "condition_id": condition_id,
                    "split": case["split"], "repetition": repetition, "base_scenario_sha256": case["scenario_sha256"],
                    "participant_order": ordering,
                    "agent_memory_isolation": "not_guaranteed_by_client"}
                run.save()
                entries.append({"run": name, **run.data["attention_trial"], "expectations": case["expectations"], "response_windows": case.get("response_windows", [])})
    plan = {"schema": "agent-experiment-lab.attention-plan/1", "created_at": now(), "split": split,
            "frozen_suite_sha256": digest(snapshot), "bindings_sha256": digest(bindings), "max_parallel": max_parallel,
            "conditions": conditions, "runs": entries, "driver": driver_identity(),
            "planned_opportunities": sum(len(entry["expectations"]) for entry in entries)}
    write(output / "plan.json", plan)
    write(output / "plan-receipt.json", {"plan_sha256": digest(plan), "prepared_at": now()})
    return {"prepared": True, "directory": str(output), "runs": len(entries),
            "planned_opportunities": plan["planned_opportunities"], "model_calls": 0,
            "plan_sha256": digest(plan), "frozen_suite_sha256": digest(snapshot)}


def verified_plan(output):
    output = Path(output)
    plan = read(output / "plan.json")
    require(digest(plan) == read(output / "plan-receipt.json")["plan_sha256"], "Suite plan changed; prepare a new experiment")
    require(digest(read(output / "frozen-suite.json")) == plan["frozen_suite_sha256"], "Frozen suite changed")
    return plan


def score(run, expectations):
    rows = []
    for item in expectations:
        turn = next((turn for turn in run.data["turns"] if turn["step"] == item["step"] and turn["participant"] == item["participant"]), None)
        actual = "not_observed"
        if turn:
            if turn.get("delivery") == "delivered" and turn.get("decision", {}).get("action") == "speak":
                actual = "speak"
            elif turn.get("delivery") == "no_response" and turn.get("decision", {}).get("action") == "pass":
                actual = "pass"
            elif turn.get("cancel_requested") and turn.get("stop_reason") == "cancelled" and turn.get("delivery") == "not_delivered":
                actual = "cancelled"
            else:
                actual = "unresolved" if turn.get("state") in ("unknown", "in_flight", "connecting", "connection_error", "abandoned") else "not_delivered"
        rows.append({**item, "actual": actual, "matched": None if item["expected"] == "optional" else actual == item["expected"],
                     "turn_id": turn["id"] if turn else None, "decision_reason": turn.get("decision", {}).get("reason") if turn else None,
                     "delivery": turn.get("delivery") if turn else None, "input": turn.get("input") if turn else None,
                     "output": turn.get("output") if turn else None})
    return rows


def suite_report(output):
    output = Path(output).resolve()
    plan = verified_plan(output)
    records = []
    for entry in plan["runs"]:
        run = Run(output / entry["run"])
        summary = report(run)
        decisions = score(run, entry["expectations"])
        windows = []
        for window in entry.get("response_windows", []):
            speech = sum(row["step"] == window["step"] and row["actual"] == "speak" for row in decisions)
            unobserved = sum(row["step"] == window["step"] and row["actual"] not in ("speak", "pass") for row in decisions)
            windows.append({**window, "speakers": speech, "unobserved": unobserved,
                            "excess_speakers": max(0, speech - window["max_speakers"]),
                            "matched": unobserved == 0 and window["min_speakers"] <= speech <= window["max_speakers"]})
        records.append({**entry, "run_id": run.data["id"], "status": run.data["status"],
                        "decisions": decisions, "response_window_results": windows, "measurements": summary["measurements"],
                        "evaluations": run.data["evaluations"], "driver": run.data["driver"],
                        "publication_checks": sum(bool(t.get("publication_check")) for t in run.data["turns"]),
                        "publication_check_ms": sum(t.get("publication_check", {}).get("elapsed_ms", 0) for t in run.data["turns"])})
    totals = {}
    for condition in plan["conditions"]:
        runs = [item for item in records if item["condition_id"] == condition]
        rows = [row for item in runs for row in item["decisions"]]
        totals[condition] = {
            "runs": len(runs), "completed_runs": sum(item["status"] == "completed" for item in runs),
            "publication_checks": sum(item["publication_checks"] for item in runs),
            "publication_check_ms": sum(item["publication_check_ms"] for item in runs),
            "planned_opportunities": len(rows), "actual_decisions": dict(Counter(row["actual"] for row in rows)),
            "expected_silence": sum(row["expected"] == "pass" for row in rows),
            "useful_passes": sum(row["expected"] == "pass" and row["actual"] == "pass" for row in rows),
            "unwanted_speech": sum(row["expected"] == "pass" and row["actual"] == "speak" for row in rows),
            "required_responses": sum(row["expected"] == "speak" for row in rows),
            "required_responses_delivered": sum(row["expected"] == "speak" and row["actual"] == "speak" for row in rows),
            "missed_required_responses": sum(row["expected"] == "speak" and row["actual"] != "speak" for row in rows),
            "unknown_or_unobserved": sum(row["actual"] in ("unresolved", "not_observed", "not_delivered") for row in rows),
            "confirmed_cancelled_drafts": sum(row["expected"] == "cancelled" and row["actual"] == "cancelled" for row in rows),
            "response_windows_matched": sum(window["matched"] for item in runs for window in item["response_window_results"]),
            "excess_speakers_in_response_windows": sum(window["excess_speakers"] for item in runs for window in item["response_window_results"]),
            "exact_artifact_checks_passed": sum(item["measurements"]["task"]["evaluator_passes"] for item in runs),
            "published_words": sum(item["measurements"]["social"]["words"] for item in runs),
            "actual_human_observations": sum(item["measurements"]["social"]["human_feedback_count"] for item in runs),
        }
    result = {"schema": "agent-experiment-lab.attention-report/1", "created_at": now(),
              "plan_sha256": digest(plan), "frozen_suite_sha256": plan["frozen_suite_sha256"], "split": plan["split"],
              "conditions": plan["conditions"], "totals": totals, "runs": records,
              "limitations": ["Expected actions are operator-authored hypotheses, not human naturalness ratings.",
                  "A delivered required response measures engagement, not whether its content satisfies the request.",
                  "Synthetic context and simulated participants are not actual human feedback.",
                  "Fresh ACP sessions do not guarantee isolated agent memory or workspaces.",
                  "Staggered scheduling changes available context and order; it is an explicit experience condition.",
                  "Repeated observations remain descriptive; order, shared installations and model variation may affect outcomes.",
                  "Recheck uses additional recorded model calls before publication; compare its latency and cost as well as speech."]}
    write(output / "attention-report.json", result)
    e = html.escape
    header = "<tr><th>Condition</th><th>Useful silence</th><th>Required replies delivered</th><th>Missed required replies</th><th>Unresolved / missing</th><th>Excess speakers in one-answer windows</th><th>Verified artifacts</th></tr>"
    rows = "".join(f'<tr><td>{e(key)}</td><td>{value["useful_passes"]}/{value["expected_silence"]}</td><td>{value["required_responses_delivered"]}/{value["required_responses"]}</td><td>{value["missed_required_responses"]}</td><td>{value["unknown_or_unobserved"]}</td><td>{value["excess_speakers_in_response_windows"]}</td><td>{value["exact_artifact_checks_passed"]}</td></tr>' for key, value in totals.items())
    cases = []
    for item in records:
        lines = "".join(f'<tr><td>{e(row["participant"])}</td><td>{e(row["category"])}</td><td>{e(row["expected"])}</td><td>{e(row["actual"])}</td><td>{e(row["decision_reason"] or "")}</td></tr>' for row in item["decisions"])
        cases.append(f'<section><h2><a href="{e(item["run"])}/report.html">{e(item["case_id"])} · {e(item["condition_id"])}</a></h2><p>{e(item["status"])}</p><table class="decisions"><tr><th>Participant</th><th>Case</th><th>Expected</th><th>Observed</th><th>Agent’s private reason</th></tr>{lines}</table></section>')
    table_style = "th,td{min-width:6rem;overflow-wrap:normal}.decisions td:last-child{min-width:16rem;width:60%;overflow-wrap:anywhere}"
    page = f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Attention experiment</title><style>{STYLE}{table_style}</style><h1>When to help, when to stay quiet</h1><p>Frozen {e(plan["split"])} cases · actual ACP decisions · no Slack messages. A pass earns credit only when explicitly returned by the agent. Failed, cancelled, and unobserved turns are kept separate.</p><table>{header}{rows}</table><p><a href="attention-report.json">Full results and evidence references</a></p><ul>{"".join("<li>" + e(note) + "</li>" for note in result["limitations"])}</ul>{"".join(cases)}</html>'
    write_bytes(output / "report.html", page.encode("utf-8"))
    return result


async def run_suite(output):
    output = Path(output).resolve()
    plan = verified_plan(output)
    require(plan["driver"] == driver_identity(), "Driver changed since preparation; prepare a new experiment")
    slots = asyncio.Semaphore(plan["max_parallel"])

    async def one(entry):
        async with slots:
            run = Run(output / entry["run"])
            with run.lock():
                # Uncertain calls are never retried by a batch. Resolve them
                # explicitly with normal run controls before continuing.
                if run.data["status"] in ("ready", "paused", "running"):
                    await Engine(run).execute()
                if run.data["status"] == "completed":
                    scenario = read(run.path / "scenario.json")
                    for evaluator in scenario.get("evaluators", []):
                        if any(item["evaluator_id"] == evaluator["id"] for item in run.data["evaluations"]):
                            continue
                        try:
                            evaluate(run, evaluator["id"])
                        except ValueError:
                            # No delivered artifact is a failed outcome, not a
                            # reason to prompt again or evaluate another author.
                            run.event("evaluation_unavailable", evaluator_id=evaluator["id"], reason="No matching delivered artifact")
                report(run)

    await asyncio.gather(*(one(entry) for entry in plan["runs"]))
    return suite_report(output)
