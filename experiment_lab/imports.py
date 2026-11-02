"""Read existing Slack trial evidence without contacting Slack or any agent."""
from pathlib import Path
import uuid

from .scenario import validate
from .storage import Run, digest, now, read


def import_slack(source, destination):
    source = Path(source).resolve()
    manifest = read(source / "run.json")
    if manifest.get("schema") != "persona-workshop.slack-trial/1":
        raise ValueError("Expected a persona-workshop.slack-trial/1 recording")
    roles = sorted({member for room in manifest["rooms"] for member in room["roster"]})
    scenario = validate({"schema": "agent-experiment-lab.scenario/1", "label": "Slack trial " + manifest["id"],
                         "participants": {role: {"label": role, "kind": "simulated_human" if role.endswith("-sim") else "support_agent"} for role in roles},
                         "rooms": {room["key"]: {"members": room["roster"]} for room in manifest["rooms"]},
                         "steps": [{"action": "cue", "room": manifest["rooms"][0]["key"], "text": "Imported recording. No prompts or messages sent."}]})
    run = Run.create(destination, scenario)
    run.data.update(experience="slack_recording", execution_kind="recording_import", status="imported", source_run_id=manifest["id"],
                    source_recording_sha256=digest((source / "run.json").read_bytes()),
                    observability="transcript_only_import", imported_at=now(), bindings_sha256=None,
                    comparison_scenario_sha256=digest([{key: room.get(key) for key in ("key", "roster", "seed_sha256", "delivered_seed_sha256")} for room in manifest["rooms"]]))
    for room in manifest["rooms"]:
        path = source / "rooms" / (room["key"] + ".json")
        if not path.exists():
            continue
        observed = read(path)
        run.evidence("slack-room-" + room["key"] + ".json", observed)
        for message in observed["messages"]:
            role = message.get("role") or message.get("name") or "unknown"
            kind = "operator_cue" if message.get("operator_cue") else scenario["participants"].get(role, {}).get("kind", "unclassified_external")
            run.data["messages"].append({"id": str(uuid.uuid4()), "seq": len(run.data["messages"]) + 1,
                                         "room": room["key"], "speaker": role, "kind": kind,
                                         "text": message["text"], "at": message["ts"], "url": message.get("url"),
                                         "source_message_id": message["ts"], "thread_ts": message.get("thread_ts")})
        run.data["observations"].append({"room": room["key"], "truncated": observed.get("truncated", False),
                                            "source": str(path), "sha256": digest(path.read_bytes())})
    run.save()
    return run
