"""Descriptive observations, separate from causal and behavioral judgments."""
from collections import Counter
import html
import json
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import urllib.parse

from .storage import digest, now, read, write

FENCE = re.compile(r"(?m)^```([a-zA-Z0-9_+.-]*)[^\n]*\n(.*?)^```\s*$", re.DOTALL)


def artifacts(run):
    items = []
    folder = run.path / "artifacts"
    folder.mkdir(mode=0o700, exist_ok=True)
    for message in run.data["messages"]:
        if message["kind"] in ("operator_cue", "membership", "scripted_context"):
            continue
        for index, match in enumerate(FENCE.finditer(message["text"])):
            raw = match[2].encode()
            sha = digest(raw)
            name = sha + ".txt"
            path = folder / name
            if not path.exists():
                path.write_bytes(raw)
                path.chmod(0o600)
            items.append({"id": message["id"] + ":" + str(index), "sha256": sha,
                          "path": "artifacts/" + name, "language": match[1],
                          "room": message["room"], "speaker": message["speaker"],
                          "message_id": message["id"], "source_url": message.get("url"),
                          "delivery": "delivered", "bytes": len(raw)})
    return items


def measures(run):
    data = run.data
    scenario = read(run.path / "scenario.json")
    turns, events = data["turns"], data["events"]
    contributions = [message for message in data["messages"] if message["kind"] not in ("operator_cue", "membership", "scripted_context")]
    per_participant = Counter(message["speaker"] for message in contributions)
    timing = [turn["elapsed_ms"] for turn in turns if turn.get("state") == "finished" and "elapsed_ms" in turn]
    available = artifacts(run)
    checks = [evaluation for evaluation in data["evaluations"] if evaluation.get("status") == "checked"]
    checked_hashes = {evaluation["artifact_sha256"] for evaluation in checks if evaluation["passed"]}
    duplicate = sum(count - 1 for count in Counter((message["room"], message["speaker"], message["text"].strip()) for message in contributions).values())
    opportunities = Counter(turn["participant"] for turn in turns)
    observed_acp = data.get("observability", "direct_acp_receipts") == "direct_acp_receipts"
    return {
        "task": {"artifacts": available, "checked_artifact_hashes": sorted(checked_hashes),
                 "evaluator_runs": len(data["evaluations"]), "evaluator_passes": sum(evaluation["passed"] for evaluation in checks),
                 "completion": "not_inferred_from_conversation", "checks_apply_to_exact_artifacts_only": True},
        "social": {"contributions": len(contributions), "per_participant": dict(per_participant),
                   "scripted_context_messages": sum(message["kind"] == "scripted_context" for message in data["messages"]),
                   "words": sum(len(message["text"].split()) for message in contributions),
                   "long_contributions_over_200_words": sum(len(message["text"].split()) > 200 for message in contributions),
                   "exact_repeat_contributions": duplicate,
                   "silent_participants": [key for key in scenario["participants"] if not per_participant[key]],
                   "prompt_opportunities": dict(opportunities) if observed_acp else None,
                   "participants_without_prompt_opportunity": [key for key in scenario["participants"] if not opportunities[key]] if observed_acp else None,
                   "voluntary_passes": sum(turn.get("delivery") == "no_response" for turn in turns) if observed_acp else None,
                   "human_feedback_count": len(data["human_feedback"]),
                   "naturalness": "requires_human_observation", "simulated_opinions_are_human_feedback": False},
        "technical": {"turns": len(turns) if observed_acp else None, "finished_turns": sum(turn["state"] == "finished" for turn in turns) if observed_acp else None,
                      "turn_states": dict(Counter(turn["state"] for turn in turns)) if observed_acp else None,
                      "delivery_states": dict(Counter(turn.get("delivery", "unknown") for turn in turns)) if observed_acp else None,
                      "median_turn_ms": statistics.median(timing) if timing else None,
                      "max_turn_ms": max(timing) if timing else None,
                      "cancellations_requested": sum(event["kind"] == "cancel_requested" for event in events) if observed_acp else None,
                      "cancellations_confirmed": sum(turn.get("stop_reason") == "cancelled" for turn in turns) if observed_acp else None,
                      "interventions_triggered": sum(event["kind"] == "intervention_triggered" for event in events) if observed_acp else None,
                      "sessions_loaded": sum(event["kind"] == "session_loaded" for event in events) if observed_acp else None,
                      "sessions_recreated": sum(event["kind"] == "session_recreated" for event in events) if observed_acp else None,
                      "permission_requests_cancelled": sum(event["kind"] == "permission_cancelled" for event in events) if observed_acp else None,
                      "tool_updates": sum(event["kind"] == "tool_update" for event in events) if observed_acp else None,
                      "final_envelope_formats": dict(Counter(turn.get("decision", {}).get("format", "unavailable") for turn in turns)) if observed_acp else None,
                      "elapsed_seconds": data.get("elapsed_seconds"),
                      "observability": data.get("observability", "direct_acp_receipts"),
                      "limits_stop_lab_client_only": True},
    }


def safe_url(value):
    value = str(value or "")
    parsed = urllib.parse.urlparse(value)
    return value if parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username else ""


STYLE = """body{font:16px/1.6 system-ui;max-width:1100px;margin:32px auto;padding:0 20px;color:#213e39;background:#f5f7f4;overflow-wrap:anywhere}h1{font-size:2rem}h2{margin-top:2rem}article,section.card{background:white;border:1px solid #d5e2dc;border-radius:12px;padding:20px;margin:12px 0}a{color:#176b64}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}code{font-size:.9em;overflow-wrap:anywhere}summary{cursor:pointer}small{color:#61766e}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(230px,100%),1fr));gap:12px}.badge{display:inline-block;background:#e4f0e9;border-radius:6px;padding:2px 8px}table{width:100%;border-collapse:collapse;display:block;overflow-x:auto}td,th{text-align:left;padding:8px;border-bottom:1px solid #d5e2dc}td{overflow-wrap:anywhere}a:focus,summary:focus{outline:3px solid #238c7b}"""


def report(run):
    measurements = measures(run)
    summary = {"schema": "agent-experiment-lab.report/1", "run_id": run.data["id"],
               "label": run.data["label"], "status": run.data["status"], "experience": run.data["experience"],
               "execution_kind": run.data.get("execution_kind", "unknown"),
               "driver": run.data.get("driver"),
               "driver_history": [event["driver"] for event in run.data["events"] if event["kind"] == "driver_started"],
               "observed_at": now(), "scenario_sha256": run.data["scenario_sha256"],
               "comparison_scenario_sha256": run.data.get("comparison_scenario_sha256", run.data["scenario_sha256"]),
               "bindings_sha256": run.data["bindings_sha256"], "measurements": measurements,
               "human_feedback": run.data["human_feedback"], "evaluations": run.data["evaluations"],
               "observations": run.data["observations"]}
    write(run.path / "summary.json", summary)
    e = html.escape
    sections = []
    for room in read(run.path / "scenario.json")["rooms"]:
        messages = [message for message in run.data["messages"] if message["room"] == room]
        transcript = []
        for message in messages:
            url = safe_url(message.get("url"))
            source = f'<a href="{e(url, quote=True)}">Source message</a>' if url else e(message["id"])
            transcript.append(f'<article id="{e(message["id"], quote=True)}"><b>{e(message["speaker"])}</b> <span class="badge">{e(message["kind"])}</span><p><small>{source}</small></p><pre>{e(message["text"])}</pre></article>')
        sections.append(f'<section><h2>{e(room)}</h2>{"".join(transcript)}</section>')
    task, social, technical = (measurements[key] for key in ("task", "social", "technical"))
    participation = "".join(f'<li>{e(key)}: {count}</li>' for key, count in social["per_participant"].items())
    metrics = (
        f'<section class="card"><h2>Task</h2><p><b>{len(task["artifacts"])}</b> published artifacts</p><p><b>{task["evaluator_passes"]}</b> passing operator evaluations of exact artifacts</p><p>Conversation claims do not establish completion.</p></section>'
        f'<section class="card"><h2>Participation</h2><p><b>{social["contributions"]}</b> contributions · {social["words"]} words</p><ul>{participation}</ul><p>{social["human_feedback_count"]} actual human observations recorded.</p></section>'
        f'<section class="card"><h2>Execution</h2><p>{technical["finished_turns"] if technical["finished_turns"] is not None else "Not observed"} completed ACP turns</p><p>{e(json.dumps(technical["delivery_states"])) if technical["delivery_states"] is not None else "Delivery receipts were not included in this import."}</p><p>Stopping observation does not prove that remote work stopped.</p></section>'
    )
    evidence = "".join(f'<li><a href="{e(item["path"], quote=True)}">{e(item["room"])} · {e(item["language"] or "text")}</a> <code>{item["sha256"]}</code></li>' for item in measurements["task"]["artifacts"])
    delivery_rows = [{key: turn.get(key) for key in ("id", "participant", "room", "state", "delivery", "reason", "message_id", "cancel_requested", "stop_reason")} for turn in run.data["turns"]]
    page = f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{e(run.data["label"])}</title><style>{STYLE}</style><h1>{e(run.data["label"])}</h1><p>{e(run.data["experience"])} · {e(run.data.get("execution_kind", "unknown"))} · {e(run.data["status"])} · {e(run.data["id"])}</p><p>Task evidence, participation, and transport observations are measured separately. Generated agreement and completion claims are not human feedback or independent verification. This report describes its recorded experience; it does not imply Slack access or authority.</p><p><a href="summary.json">Machine-readable report</a></p><div class="grid">{metrics}</div><h2>Exact artifacts</h2><ul>{evidence or "<li>No delivered artifact observed.</li>"}</ul><details><summary>All measurements</summary><pre>{e(json.dumps(measurements, indent=2))}</pre></details><details><summary>Drafts and delivery receipts</summary><pre>{e(json.dumps(delivery_rows, indent=2))}</pre></details><details><summary>Operator evaluator receipts</summary><pre>{e(json.dumps(run.data["evaluations"], indent=2))}</pre></details><details><summary>Actual human feedback</summary><pre>{e(json.dumps(run.data["human_feedback"], indent=2))}</pre></details>{"".join(sections)}</html>'
    path = run.path / "report.html"
    observation_links = []
    for item in run.data["observations"]:
        reference = item.get("evidence", {}).get("path", "")
        if reference.startswith("evidence/") and ".." not in reference and "\\" not in reference:
            label = " · ".join(str(item[key]) for key in ("participant", "room", "resource") if item.get(key)) or "Recorded observation"
            observation_links.append(f'<li><a href="{e(reference, quote=True)}">{e(label)}</a> · {e(item.get("classification", "recorded evidence"))}</li>')
    page += '<section><h2>Recorded observations</h2><p>Management responses are service-reported evidence. They do not establish behavioral quality.</p><ul>' + ("".join(observation_links) or '<li>No management observation references recorded.</li>') + '</ul></section>'
    path.write_text(page)
    path.chmod(0o600)
    return summary


def evaluate(run, evaluator_id):
    scenario = read(run.path / "scenario.json")
    if digest(scenario) != run.data["scenario_sha256"]:
        raise ValueError("Scenario changed since capture; evaluate a new run with the new acceptance criteria")
    evaluator = next((item for item in scenario.get("evaluators", []) if item["id"] == evaluator_id), None)
    if not evaluator:
        raise ValueError("Unknown operator-defined evaluator")
    candidates = [item for item in artifacts(run) if item["room"] == evaluator["room"]
                  and (not evaluator.get("language") or item["language"] == evaluator["language"])
                  and (not evaluator.get("participant") or item["speaker"] == evaluator["participant"])]
    if not candidates:
        raise ValueError("No matching delivered artifact; nothing to evaluate")
    artifact = candidates[-1]
    content = (run.path / artifact["path"]).read_bytes()
    if digest(content) != artifact["sha256"]:
        raise ValueError("Artifact changed since observation")
    command = evaluator["command"]
    receipt = {"id": str(len(run.data["evaluations"]) + 1), "evaluator_id": evaluator_id,
               "scenario_sha256": run.data["scenario_sha256"],
               "started_at": now(), "artifact_sha256": artifact["sha256"], "artifact_id": artifact["id"],
               "artifact_speaker": artifact["speaker"], "source_message_id": artifact["message_id"],
               "command_sha256": digest(command), "source": "separate_operator_process",
               "program_files": [{"path": value, "sha256": digest(Path(value).read_bytes())} for value in command if Path(value).is_file()]}
    run.data["evaluations"].append(receipt)
    run.save()
    try:
        # A scenario evaluator is executable operator configuration. It is never
        # taken from an agent's proposed commands or automatically trusted code.
        with tempfile.TemporaryDirectory(prefix="agent-lab-evaluator-") as directory:
            result = subprocess.run(command, input=json.dumps({"artifact": artifact, "content": content.decode()}).encode(),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=directory,
                                    timeout=evaluator.get("timeout_seconds", 20), check=False)
        if len(result.stdout) > 1_000_000 or len(result.stderr) > 1_000_000:
            raise ValueError("Evaluator output limit exceeded")
        if any(not Path(item["path"]).is_file() or digest(Path(item["path"]).read_bytes()) != item["sha256"]
               for item in receipt["program_files"]):
            raise ValueError("An evaluator program changed during the check; its result is not attributable to the recorded version")
        details = json.loads(result.stdout)
        checks = details.get("checks", [])
        if details.get("artifact_sha256") != artifact["sha256"] or not checks or any(not isinstance(item.get("passed"), bool) or not isinstance(item.get("name"), str) for item in checks):
            raise ValueError("Evaluator must return named boolean checks for this exact artifact hash")
        receipt.update(status="checked", passed=result.returncode == 0 and all(item["passed"] for item in checks),
                       exit_code=result.returncode, checks=checks,
                       evidence=run.evidence(f'evaluator-{receipt["id"]}.json', {"result": details, "stderr": result.stderr.decode(errors="replace")}))
    except Exception as exc:
        receipt.update(status="error", passed=False, error_type=type(exc).__name__)
    receipt["finished_at"] = now()
    run.save()
    return receipt


def compare(runs, output):
    summaries = [report(run) for run in runs]
    manifests = [read(run.path / "scenario.json") for run in runs]
    same_scenario = len({item["comparison_scenario_sha256"] for item in summaries}) == 1
    same_bindings = len({item["bindings_sha256"] for item in summaries}) == 1 if all(item["bindings_sha256"] for item in summaries) else None
    same_experience = len({item["experience"] for item in summaries}) == 1
    same_driver = len({digest(driver) for item in summaries for driver in [item["driver"], *item["driver_history"]]}) == 1 if all(item["driver"] for item in summaries) else None
    rows = [{"run_id": item["run_id"], "label": item["label"], "status": item["status"],
             "experience": item["experience"], "measurements": item["measurements"]} for item in summaries]
    result = {"schema": "agent-experiment-lab.comparison/1", "created_at": now(), "runs": rows,
              "comparability": {"same_scenario": same_scenario, "same_bindings": same_bindings,
                                "same_experience": same_experience,
                                "same_driver": same_driver,
                                "same_rosters": all(item["participants"] == manifests[0]["participants"] for item in manifests),
                                "interpretation": "descriptive_only", "causal_effect_established": False},
              "note": "Even matched configurations do not establish causal improvement. Record repeated runs, confounds, and actual human observations separately."}
    output = Path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    write(output / "comparison.json", result)
    header = "<tr><th>Run</th><th>Experience</th><th>Contributions</th><th>Artifact checks passed</th><th>Uncertain turns</th><th>Human feedback</th></tr>"
    table = "".join(f'<tr><td>{html.escape(item["label"])}</td><td>{html.escape(item["experience"])}</td><td>{item["measurements"]["social"]["contributions"]}</td><td>{item["measurements"]["task"]["evaluator_passes"]}</td><td>{item["measurements"]["technical"]["turn_states"].get("unknown", 0) if item["measurements"]["technical"]["turn_states"] is not None else "not observed"}</td><td>{item["measurements"]["social"]["human_feedback_count"]}</td></tr>' for item in summaries)
    path = output / "report.html"
    path.write_text(f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Experiment comparison</title><style>{STYLE}</style><h1>Experiment comparison</h1><p>{html.escape(result["note"])}</p><table>{header}{table}</table><h2>Comparability</h2><pre>{html.escape(json.dumps(result["comparability"], indent=2))}</pre><p><a href="comparison.json">Full machine-readable comparison</a></p></html>')
    path.chmod(0o600)
    return result
