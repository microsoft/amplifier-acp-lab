"""Private, atomic checkpoints and immutable referenced evidence."""
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from . import __version__


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(value).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def driver_identity():
    return {"name": "agent-experiment-lab", "version": __version__,
            "source_sha256": digest({item.name: digest(item.read_bytes()) for item in sorted(Path(__file__).parent.glob('*.py'))})}


def write(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".checkpoint-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Run:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.data = read(self.path / "run.json")

    @classmethod
    def create(cls, path, scenario, bindings=None):
        path = Path(path).resolve()
        path.mkdir(mode=0o700, parents=True, exist_ok=False)
        write(path / "scenario.json", scenario)
        if bindings is not None:
            write(path / "bindings.json", bindings)
        write(path / "run.json", {
            "schema": "agent-experiment-lab.run/1", "id": str(uuid.uuid4()),
            "label": scenario["label"], "created_at": now(), "status": "ready",
            "experience": "lab_acp", "scenario_sha256": digest(scenario),
            "execution_kind": "protocol_fixture" if all(value["kind"] == "protocol_fixture" for value in scenario["participants"].values()) else "configured_acp_endpoints",
            "bindings_sha256": digest(bindings or {}), "cursor": 0,
            "driver": driver_identity() if bindings is not None else None,
            "members": {key: value["members"][:] for key, value in scenario["rooms"].items()},
            "sessions": {}, "turns": [], "messages": [], "events": [],
            "evaluations": [], "human_feedback": [], "observations": [],
        })
        return cls(path)

    def save(self):
        write(self.path / "run.json", self.data)

    def event(self, kind, **values):
        record = {"seq": len(self.data["events"]) + 1, "at": now(), "kind": kind, **values}
        self.data["events"].append(record)
        self.save()
        return record

    def evidence(self, name, value):
        path = self.path / "evidence" / name
        write(path, value)
        return {"path": str(path.relative_to(self.path)), "sha256": digest(path.read_bytes())}

    @contextlib.contextmanager
    def lock(self):
        # Exclusive create works on Windows and Unix; a killed process leaves a
        # conspicuous lock. Explicit unlock is preferable to duplicate prompts.
        path = self.path / ".runner.lock"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise ValueError("Run is locked; inspect the process, then use unlock if it has stopped") from exc
        with os.fdopen(fd, "w") as stream:
            json.dump({"pid": os.getpid(), "created_at": now()}, stream)
        try:
            self.data = read(self.path / "run.json")
            yield
        finally:
            path.unlink(missing_ok=True)
