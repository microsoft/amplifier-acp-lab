"""Minimal ACP v1 stdio client. Endpoint ownership stays outside the lab."""
import asyncio
import json
import os
from pathlib import Path
import signal

from . import __version__


class ProtocolError(RuntimeError):
    pass


class AuthenticationRequired(ProtocolError):
    def __init__(self):
        super().__init__("Agent sign-in required. Sign in to the configured ACP agent on its host using the same service account, then reconnect. The lab is noninteractive and does not run sign-in flows.")


def authentication(info):
    def safe(value):
        return "".join(c for c in value if c.isprintable())[:200] if isinstance(value, str) else ""
    methods = info.get("authMethods", [])
    return {"profile": "acp-preauthenticated/1", "interactive": False,
            "methods": [{key: safe(item.get(key)) for key in ("id", "name", "type")} for item in methods[:16] if isinstance(item, dict)] if isinstance(methods, list) else [],
            "instructions": "Sign in to the configured ACP agent on its host using the same service account, then reconnect. No sign-in command or URL is executed automatically."}


class Client:
    def __init__(self, endpoint, observe):
        self.endpoint, self.observe = endpoint, observe
        self.process = None
        self.next_id = 0
        self.session = None
        self.info = None
        self.write_lock = asyncio.Lock()

    async def start(self):
        # Explicit inheritance avoids carrying unrelated access tokens to agents.
        names = ("PATH", "HOME", "USER", "LANG", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "SSL_CERT_FILE", "SSL_CERT_DIR", "SSH_AUTH_SOCK")
        env = {name: os.environ[name] for name in names if name in os.environ}
        env.update(self.endpoint.get("env", {}))
        for name, path in self.endpoint.get("secret_env", {}).items():
            env[name] = Path(path).expanduser().read_text().strip()
        command = self.endpoint["command"]
        self.process = await asyncio.create_subprocess_exec(*command,
            cwd=self.endpoint.get("launch_cwd") or None, env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=4 * 1024 * 1024,
            start_new_session=os.name != "nt")
        self.info = await asyncio.wait_for(self.request("initialize", {
            "protocolVersion": 1, "clientInfo": {"name": "agent-experiment-lab", "version": __version__},
            "clientCapabilities": {},
        }), 30)
        if self.info.get("protocolVersion") != 1:
            raise ProtocolError("Endpoint did not negotiate ACP v1")
        self.observe("initialized", agent_info=self.info.get("agentInfo"), capabilities=self.info.get("agentCapabilities", {}), authentication=authentication(self.info))

    async def open_session(self, previous=None):
        params = {"cwd": self.endpoint["cwd"], "mcpServers": []}
        if previous and self.info.get("agentCapabilities", {}).get("loadSession"):
            params["sessionId"] = previous
            await asyncio.wait_for(self.request("session/load", params), 30)
            self.session = previous
            self.observe("session_loaded", session_id=previous)
        else:
            result = await asyncio.wait_for(self.request("session/new", params), 30)
            self.session = result.get("sessionId")
            if not isinstance(self.session, str) or not self.session:
                raise ProtocolError("Endpoint returned no session ID")
            self.observe("session_recreated" if previous else "session_created", session_id=self.session)
        return self.session

    async def send(self, value):
        async with self.write_lock:
            self.process.stdin.write((json.dumps({"jsonrpc": "2.0", **value}) + "\n").encode())
            await self.process.stdin.drain()

    async def cancel(self):
        await self.send({"method": "session/cancel", "params": {"sessionId": self.session}})

    async def request(self, method, params, update=None):
        self.next_id += 1
        request_id = self.next_id
        await self.send({"id": request_id, "method": method, "params": params})
        while True:
            line = await self.process.stdout.readline()
            if not line:
                raise ProtocolError("ACP closed before replying")
            value = json.loads(line)
            if value.get("jsonrpc") != "2.0":
                raise ProtocolError("Invalid JSON-RPC frame")
            if "method" not in value and value.get("id") == request_id:
                if "error" in value:
                    if value["error"].get("code") == -32000:
                        self.observe("agent_sign_in_required", authentication=authentication(self.info or {}))
                        raise AuthenticationRequired()
                    raise ProtocolError("ACP request rejected (see endpoint logs)")
                return value.get("result", {})
            if "method" in value and "id" in value:
                if value["method"] == "session/request_permission":
                    self.observe("permission_cancelled", session_id=value.get("params", {}).get("sessionId"))
                    await self.send({"id": value["id"], "result": {"outcome": {"outcome": "cancelled"}}})
                else:
                    await self.send({"id": value["id"], "error": {"code": -32601, "message": "Client capability not offered"}})
                    self.observe("unsupported_callback", method=value["method"])
            elif value.get("method") == "session/update" and update:
                message = value.get("params", {})
                if message.get("sessionId") != self.session:
                    raise ProtocolError("Update addressed a different ACP session")
                await update(message.get("update", {}))

    async def prompt(self, text, timeout, on_chunk=None):
        parts, characters = [], 0

        async def update(message):
            nonlocal characters
            kind = message.get("sessionUpdate")
            if kind == "agent_message_chunk" and message.get("content", {}).get("type") == "text":
                chunk = message["content"]["text"]
                characters += len(chunk)
                if characters > 250_000:
                    raise ProtocolError("ACP output exceeds the observation limit")
                parts.append(chunk)
                if on_chunk:
                    await on_chunk(chunk)
            elif kind in ("tool_call", "tool_call_update"):
                self.observe("tool_update", tool_id=message.get("toolCallId"), status=message.get("status"), title=message.get("title"))
            elif kind == "usage_update":
                self.observe("usage", usage={key: message[key] for key in ("used", "size", "cost") if key in message})
            # Reasoning and raw tool content are not copied into the lab report.

        try:
            result = await asyncio.wait_for(self.request("session/prompt", {
                "sessionId": self.session, "prompt": [{"type": "text", "text": text}],
            }, update), timeout)
            return {"text": "".join(parts), "stop_reason": result.get("stopReason", "unknown")}
        except asyncio.TimeoutError:
            try:
                await self.cancel()
                self.observe("timeout_cancel_requested")
            except (OSError, RuntimeError):
                pass
            raise

    async def close(self):
        if not self.process:
            return
        if self.process.returncode is None:
            try:
                if os.name != "nt":
                    os.killpg(self.process.pid, signal.SIGTERM)
                else:
                    self.process.terminate()
                await asyncio.wait_for(self.process.wait(), 3)
            except (ProcessLookupError, asyncio.TimeoutError):
                if self.process.returncode is None:
                    if os.name != "nt":
                        os.killpg(self.process.pid, signal.SIGKILL)
                    else:
                        self.process.kill()
                    await self.process.wait()
