"""Independent checks over records returned by the actual components."""
import hashlib
import json


def artifact_oracle(workshop, project_id, revision_id):
    profile = workshop.api("GET", f"/api/v1/projects/{project_id}/revisions/{revision_id}/export")
    manifest = profile["manifest"]
    required_files = {"communication.md", "working-style.md", "claims.json", "evaluation-summary.json"}
    assert set(manifest["files"]) == required_files, profile
    assert set(profile["files"]) == required_files | {"manifest.json"}, profile
    assert json.loads(profile["files"]["manifest.json"]) == manifest
    assert set(manifest["required_context"]) == {"communication.md", "working-style.md"}, manifest
    assert manifest["subject_key"] == project_id and manifest["revision"] == revision_id, manifest
    assert "concise" in profile["files"]["communication.md"].lower(), profile
    assert "evidence" in profile["files"]["working-style.md"].lower(), profile
    for name, expected in profile["manifest"]["files"].items():
        assert name in profile["files"], name
        assert hashlib.sha256(profile["files"][name].encode()).hexdigest() == expected
    return profile


def recovered_job_oracle(events, recovered, project_id, request_id):
    accepted = [event for event in events if event["operation"] == "build"]
    assert len(accepted) == 1, accepted
    submission = accepted[0]
    assert submission["request_id"] == request_id and submission["reply"] == "deliberately_lost", submission
    job = recovered["job"]
    assert recovered["outcome"] == "recorded" and job["status"] == "complete", recovered
    assert job["id"] == submission["job_id"] and job["project_id"] == project_id, job
    assert job["kind"] == "build" and job["submission"]["request_id"] == request_id, job
    return job


def source_identity_oracle(source, room, request_id, work, original_text=None):
    publication = source["publication"]
    assert source["request_id"] == publication["message_id"] == request_id
    assert publication["state"] == "saved" and publication["conversation_id"] == room["id"]
    message = next(message for message in room["messages"] if message["id"] == request_id)
    assert message["role"] == "user"
    if original_text is not None:
        assert message["text"] == original_text
    delivery = next(row for row in source["items"] if row["agent_id"] == "default")
    assert delivery["message_id"] == request_id and delivery["source_sequence"] == publication["source_sequence"]
    fact = delivery["source_delivery"]
    assert len(fact["sources"]) == 1
    # The Conversation owns revision meaning. Join its original-source facts
    # without reproducing a particular implementation's revision algorithm.
    revision = fact["sources"][0]["revision"]
    assert isinstance(revision, str) and revision
    expected_sources = [{"id": request_id, "revision": revision, "occurredAt": publication["created_at"]}]
    assert fact["input_id"] == delivery["id"] and fact["sources"] == expected_sources
    receipts = fact["receipt"]["receipts"]
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt["sourceId"] == request_id and receipt["revision"] == revision
    assert receipt["occurredAt"] == publication["created_at"] and receipt["inputId"] == delivery["id"]
    origin = work["source_input"]
    assert origin["inputId"] == delivery["id"] and origin["sources"] == expected_sources
    assert origin["sessionId"] == delivery["session_id"]
    assert work["source"]["conversation_id"] == room["id"] and work["source"]["message_id"] == request_id
    assert any(ref["id"] == work["id"] and ref["inputId"] == delivery["id"] for ref in receipt["work"])
    return {"request_id": request_id, "input_id": delivery["id"], "source_revision": revision,
            "conversation_id": room["id"], "work_id": work["id"]}


