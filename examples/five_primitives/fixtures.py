"""Local test doubles at model and tool-transport edges, never record owners."""
import json
import http.client
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote


class LocalServer:
    def __init__(self, dispatch, *, with_headers=False):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(405)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_DELETE = do_GET

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                response = dispatch(body, dict(self.headers)) if with_headers else dispatch(body)
                if body.get("jsonrpc") == "2.0" and "id" not in body:
                    self.send_response(202)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if response is None:  # Deliberately lose one invocation reply.
                    self.close_connection = True
                    return
                if isinstance(response, tuple):
                    status, response = response
                    encoded = json.dumps(response).encode()
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                    return
                if isinstance(response, bytes):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Content-Length", str(len(response)))
                    self.end_headers()
                    self.wfile.write(response)
                    return
                encoded = json.dumps(response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class WorkshopMCP:
    """Translate two ordinary MCP tools to existing Workshop APIs.

    This example owns no durable job state. The exact lookup key and job/result
    belong to Workshop. ``events`` is an independent test trace, not a ledger.
    """
    def __init__(self, api, project, submit=None):
        self.api, self.project = api, project
        self.events = []
        self.submit = submit or (lambda body: api("POST", f"/api/v1/projects/{project['id']}/builds", body))

    def dispatch(self, request):
        method, params = request.get("method"), request.get("params", {})
        result = {}
        if method == "initialize":
            result = {"protocolVersion": params["protocolVersion"], "capabilities": {"tools": {}},
                      "serverInfo": {"name": "workshop-reference-adapter", "version": "1"}}
        elif method == "tools/list":
            schema = {"type": "object", "properties": {"request_id": {"type": "string"}},
                      "required": ["request_id"], "additionalProperties": False}
            result = {"tools": [
                {"name": "profile_build", "description": "Build the fixture project through Workshop. A lost reply is not permission to repeat.",
                 "inputSchema": schema, "annotations": {"readOnlyHint": False, "openWorldHint": False}},
                {"name": "profile_inspect", "description": "Inspect Workshop's exact caller-key record and its completed artifact. Never starts work.",
                 "inputSchema": schema, "annotations": {"readOnlyHint": True, "openWorldHint": False}},
            ]}
        elif method == "tools/call":
            key = params["arguments"]["request_id"]
            base = f"/api/v1/projects/{self.project['id']}"
            if params["name"] == "profile_build":
                self.events.append({"operation": "build", "request_id": key})
                try:
                    record = self.submit({"expected_revision": self.project["revision"], "request_id": key})
                except http.client.RemoteDisconnected:
                    # The downstream service reply was lost. MCP itself remains
                    # healthy and reports failure honestly; never infer rejection.
                    self.events[-1]["acceptance"] = "unknown"
                    unknown = {"acceptance": "unknown", "request_id": key,
                               "next_step": "Inspect the existing submission; do not resubmit."}
                    return {"jsonrpc": "2.0", "id": request.get("id"), "result": {
                        "isError": True, "structuredContent": unknown,
                        "content": [{"type": "text", "text": json.dumps(unknown)}]}}
            elif params["name"] == "profile_inspect":
                self.events.append({"operation": "inspect", "request_id": key})
                record = self.api("GET", base + "/jobs?request_id=" + quote(key, safe=""))
                job = record.get("job")
                deadline = time.monotonic() + 10
                while job and job.get("status") in {"queued", "running"} and time.monotonic() < deadline:
                    time.sleep(.1)
                    record = self.api("GET", base + "/jobs?request_id=" + quote(key, safe=""))
                    job = record.get("job")
                if job and job.get("status") == "complete":
                    record["artifact"] = self.api("GET", base + "/revisions/" + job["result_id"])
            else:
                raise ValueError("Unsupported fixture tool")
            result = {"content": [{"type": "text", "text": json.dumps(record)}],
                      "structuredContent": record, "isError": False}
        elif method not in {"ping", "notifications/initialized"}:
            return {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32601, "message": "Method not found"}}
        return {"jsonrpc": "2.0", "id": request.get("id"), "result": result}


def structured(value):
    """Decode the actual runtime's tool result, without inventing successful data."""
    if isinstance(value, str):
        try:
            return structured(json.loads(value))
        except (ValueError, TypeError):
            return value
    if isinstance(value, dict):
        if "structuredContent" in value:
            return value["structuredContent"]
        if value.get("structured_content") is not None:
            return value["structured_content"]
        if "output" in value:
            return structured(value["output"])
        if "result" in value:
            return structured(value["result"])
        content = value.get("content")
        if isinstance(content, str):
            return structured(content)
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    found = structured(block.get("text", ""))
                    if isinstance(found, dict):
                        return found
    return value


def tool_failed(value):
    """Read only explicit protocol status, never classify result prose."""
    if isinstance(value, str):
        try:
            return tool_failed(json.loads(value))
        except (ValueError, TypeError):
            return None
    if isinstance(value, dict):
        if "isError" in value:
            return value["isError"] is True
        if "is_error" in value:
            return value["is_error"] is True
        if "success" in value:
            return value["success"] is False
        if "result" in value:
            return tool_failed(value["result"])
    return None


class ScriptedProvider:
    """Deterministic model endpoint; the actual engine still executes the tools.

    The driver supplies a bounded sequence of decisions. This proves composition
    and recovery, not that an autonomous model would make those decisions.
    """
    def __init__(self, trace):
        self.plan, self.results, self.raw_results, self.events = [], {}, {}, []
        self.trace, self.source_input = trace, None
        self.active, self.active_call_id = None, None
        self.failure = None
        self.finished = threading.Event()

    def set_plan(self, plan):
        assert self.active is None
        self.plan = list(plan)
        self.finished.clear()

    def dispatch(self, body):
        try:
            return self._dispatch(body)
        except Exception as error:
            self.failure = f"{type(error).__name__}: {error}"
            self.events.append({"fixture_failure": self.failure})
            return 500, {"error": {"message": self.failure}}

    def _dispatch(self, body):
        self.trace.write(json.dumps(body) + "\n")
        self.trace.flush()
        def frame(delta, finish=None):
            return b"data: " + json.dumps({"id": "reference", "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}).encode() + b"\n\n"
        # Unified's installed naming helper makes bounded, non-streaming utility
        # calls outside the foreground loop. Keep them visible and defer naming;
        # they neither consume this work script nor become user-facing output.
        if not body.get("tools") and (body.get("metadata") or {}).get("stream") is False and body.get("max_output_tokens") == 256:
            self.events.append({"utility_request": "bounded_nonstreaming", "response": "defer"})
            return frame({"content": '{"action":"defer","name":null,"description":null}'}) + frame({}, "stop") + b"data: [DONE]\n\n"
        text = json.dumps(body["messages"])
        matches = re.findall(r'source_input_id: \\\"([^\\]+)\\\"', text)
        if matches:
            self.source_input = matches[-1]
        # A tool reply always precedes the next scripted decision.
        if self.active:
            last = next((m for m in reversed(body["messages"]) if m.get("role") == "tool"
                         and m.get("tool_call_id") == self.active_call_id), None)
            assert last is not None, f"Missing actual result for {self.active_call_id}"
            self.raw_results[self.active] = last.get("content")
            self.results[self.active] = structured(last.get("content"))
            self.events.append({"result_for": self.active, "result": self.results[self.active],
                                "failed": tool_failed(last.get("content"))})
            self.active, self.active_call_id = None, None
        if not self.plan:
            raise AssertionError("Unexpected provider request: the script is exhausted")
        step = self.plan.pop(0)
        if isinstance(step, dict) and "failure" in step:
            self.finished.set()
            self.events.append({"injected_provider_failure": step["failure"]})
            return 400, {"error": {"message": step["failure"]}}
        if isinstance(step, str) or isinstance(step, dict) and "final" in step:
            text = step["final"](self) if isinstance(step, dict) else step
            self.finished.set()
            delta, finish = {"content": text}, "stop"
        else:
            label, tool, arguments = step
            arguments = arguments(self) if callable(arguments) else arguments
            aliases = [t["function"]["name"] for t in body.get("tools", [])]
            alias = next((name for name in aliases if name.endswith("_" + tool)), None)
            if alias is None:
                raise AssertionError(f"Actual engine did not expose {tool}: {aliases}")
            self.active = label
            self.events.append({"call": label, "tool": tool, "arguments": arguments})
            self.active_call_id = "fixture-" + str(len(self.events))
            delta = {"tool_calls": [{"index": 0, "id": self.active_call_id,
                      "type": "function", "function": {"name": alias, "arguments": json.dumps(arguments)}}]}
            finish = "tool_calls"
        return frame(delta) + frame({}, finish) + b"data: [DONE]\n\n"
