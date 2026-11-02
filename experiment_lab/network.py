"""Optional authenticated management calls; no redirect or insecure TLS fallback."""
import json
from pathlib import Path
import urllib.parse
import urllib.request

from .storage import read


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def api(origin, token_file, path, payload=None, method=None):
    parsed = urllib.parse.urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Management endpoint must be an HTTPS origin")
    if not path.startswith("/api/v1/") or ".." in path or "#" in path:
        raise ValueError("Use an /api/v1/ resource path")
    method = method or ("GET" if payload is None else "POST")
    if method not in ("GET", "POST", "PUT"):
        raise ValueError("Unsupported management method")
    token = Path(token_file).expanduser().read_text().strip()
    if token.startswith("{"):
        token = json.loads(token)["token"]
    request = urllib.request.Request(origin.rstrip("/") + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method=method)
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
        data = response.read(8_000_001)
    if len(data) > 8_000_000:
        raise ValueError("Management observation exceeds the size limit")
    return json.loads(data)


def public_transcript(run):
    """Only delivered room messages, never turn prompts, private drafts or bindings."""
    participants = read(run.path / "scenario.json")["participants"]
    messages = []
    for message in run.data.get("messages", []):
        if message["kind"] not in ("simulated_human", "support_agent", "human", "operator_cue", "membership", "protocol_fixture"):
            raise ValueError("Unknown public transcript role")
        item = {key: message[key] for key in ("id", "speaker", "kind", "room", "text")}
        item["at"] = message.get("at")
        item["speaker"] = participants.get(message["speaker"], {}).get("label", message["speaker"])
        messages.append(item)
    if len(messages) > 500 or sum(len(m["text"].encode()) for m in messages) > 1_000_000 or any(len(m["text"].encode()) > 128_000 for m in messages):
        raise ValueError("Public transcript exceeds the fleet report limit")
    return messages


def submit(run, summary, origin, token_file, report_url=None, include_transcript=False):
    messages = public_transcript(run) if include_transcript else None
    payload = {"label": run.data["label"], "run_id": run.data["id"], "status": run.data["status"],
               "summary": f'{run.data["experience"]} experiment report; scenario steps and measurements are observations, not human endorsement or broad completion verification.',
               "measurements": summary["measurements"],
               "participants": list(read(run.path / "scenario.json")["participants"])}
    if report_url:
        from .analysis import safe_url
        if not safe_url(report_url):
            raise ValueError("Report URL must be HTTP(S)")
        payload["report_url"] = report_url
    receipt = api(origin, token_file, "/api/v1/experiments", payload)
    run.event("fleet_report_submitted", origin=origin, receipt=receipt)
    if messages is not None:
        result = api(origin, token_file, f'/api/v1/experiments/{receipt["id"]}/transcript',
                     {"expected_revision": receipt["revision"], "messages": messages}, method="PUT")
        run.event("fleet_transcript_submitted", origin=origin, receipt=result)
        receipt["transcript"] = result
    return receipt
