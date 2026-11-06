"""Lab policy and ordered observations around the official ACP Python SDK."""
import asyncio
import json
import os
from pathlib import Path
import signal
from acp import connect_to_agent
from acp.connection import StreamDirection
from acp.exceptions import RequestError
from acp.schema import (InitializeRequest, NewSessionRequest, LoadSessionRequest,
                        PromptRequest, SessionNotification, RequestPermissionResponse)
from acp.utils import model_to_kwargs
from pydantic import ValidationError

from . import __version__


class ProtocolError(RuntimeError):
    pass


class AuthenticationRequired(ProtocolError):
    def __init__(self):
        super().__init__("Agent sign-in required. Sign in to the configured ACP agent on its host using the same service account, then reconnect. The lab is noninteractive and does not run sign-in flows.")


def wire(model):
    return model.model_dump(mode="json", by_alias=True, exclude_none=True, exclude_unset=True)


class _Callbacks:
    def __init__(self, owner):
        self.owner = owner

    async def session_update(self, session_id, update, **kwargs):
        # Ordered collection uses the SDK observer, before its independently
        # scheduled callbacks. No protocol framing or correlation is duplicated.
        pass

    async def request_permission(self, session_id, tool_call, options, **kwargs):
        self.owner.observe("permission_cancelled", session_id=session_id)
        return RequestPermissionResponse.model_validate({"outcome": {"outcome": "cancelled"}})


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
        self.session = None
        self.info = None
        self.connection = None
        self.update_handler = None
        self.update_queue = asyncio.Queue(maxsize=1024)
        self.update_worker = None
        self.failed = None
        self.fatal = None

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
        self.fatal = asyncio.get_running_loop().create_future()
        self.connection = connect_to_agent(_Callbacks(self), self.process.stdin,
                                           self.process.stdout, observers=[self._stream_event])
        self.update_worker = asyncio.create_task(self._collect_updates())
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
            self.session = previous
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

    async def cancel(self):
        await asyncio.wait_for(self.connection.cancel(session_id=self.session), 5)

    def _fail(self, error):
        if self.failed is None:
            self.failed = error
        if self.fatal is not None and not self.fatal.done():
            self.fatal.set_result(self.failed)

    def _stream_event(self, event):
        if event.direction != StreamDirection.INCOMING:
            return
        value = event.message
        if "id" in value and value.get("method") and value["method"] != "session/request_permission":
            self.observe("unsupported_callback", method=value["method"])
        if value.get("method") != "session/update" or "id" in value:
            return
        try:
            message = SessionNotification.model_validate(value.get("params"))
            if self.update_handler:
                if message.session_id != self.session:
                    raise ProtocolError("Update addressed a different ACP session")
                self.update_queue.put_nowait((self.update_handler, wire(message.update)))
        except Exception as error:
            self._fail(error if isinstance(error, ProtocolError) else
                       ProtocolError("Invalid or excessive ACP updates"))

    async def _collect_updates(self):
        while True:
            handler, message = await self.update_queue.get()
            try:
                if self.failed is None:
                    await handler(message)
            except Exception as error:
                self._fail(error)
            finally:
                self.update_queue.task_done()

    async def request(self, method, params, update=None):
        if self.failed:
            raise self.failed
        methods = {"initialize": (InitializeRequest, self.connection.initialize),
                   "session/new": (NewSessionRequest, self.connection.new_session),
                   "session/load": (LoadSessionRequest, self.connection.load_session),
                   "session/prompt": (PromptRequest, self.connection.prompt)}
        if method not in methods:
            raise ProtocolError("Unsupported ACP request method")
        model, call = methods[method]
        self.update_handler = update
        operation = asyncio.create_task(call(**model_to_kwargs(model.model_validate(params), model)))
        drain = None
        try:
            await asyncio.wait([operation, self.fatal], return_when=asyncio.FIRST_COMPLETED)
            if self.failed:
                raise self.failed
            result = operation.result()
            # The SDK owns responses. Drain only the application observations
            # already queued before that response, including slow on_chunk hooks.
            drain = asyncio.create_task(self.update_queue.join())
            await asyncio.wait([drain, self.fatal], return_when=asyncio.FIRST_COMPLETED)
            if self.failed:
                raise self.failed
            return wire(result)
        except RequestError as error:
            if error.code == -32000:
                self.observe("agent_sign_in_required", authentication=authentication(self.info or {}))
                raise AuthenticationRequired() from None
            raise ProtocolError("ACP request rejected (see endpoint logs)") from None
        except ValidationError:
            raise ProtocolError("ACP response violated its SDK schema") from None
        except (ConnectionError, OSError):
            raise ProtocolError("ACP closed before replying; delivery is unknown") from None
        finally:
            self.update_handler = None
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            if drain is not None and not drain.done():
                drain.cancel()
                await asyncio.gather(drain, return_exceptions=True)

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
        if self.connection:
            await self.connection.close()
        if self.update_worker:
            self.update_worker.cancel()
            await asyncio.gather(self.update_worker, return_exceptions=True)
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
